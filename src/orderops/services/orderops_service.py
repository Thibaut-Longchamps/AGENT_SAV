from collections.abc import Callable
from types import TracebackType
from typing import Protocol

from orderops.access import AppUser
from orderops.domain.enums import OrderStatus
from orderops.domain.exceptions import (
    CustomerNotFoundError,
    DeliveryNotFoundError,
    IdempotencyConflictError,
    IncidentNotAllowedError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from orderops.domain.models import (
    CreateIncidentCommand,
    Customer,
    Delivery,
    Incident,
    IncidentCreationResult,
    Order,
    ProductStock,
)


class OrderRepository(Protocol):
    async def get_by_id(self, order_id: str) -> Order | None: ...


class CustomerRepository(Protocol):
    async def get_by_id(self, customer_id: str) -> Customer | None: ...


class InventoryRepository(Protocol):
    async def get_by_product(self, product_id: str) -> ProductStock | None: ...


class DeliveryRepository(Protocol):
    async def get_by_order(self, order_id: str) -> Delivery | None: ...


class IncidentRepository(Protocol):
    async def create_or_get(self, command: CreateIncidentCommand) -> tuple[Incident, bool, str]: ...


class AuditRepository(Protocol):
    async def add(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        outcome: str,
        details: dict[str, object],
    ) -> None: ...


class UnitOfWork(Protocol):
    @property
    def orders(self) -> OrderRepository: ...

    @property
    def customers(self) -> CustomerRepository: ...

    @property
    def inventory(self) -> InventoryRepository: ...

    @property
    def deliveries(self) -> DeliveryRepository: ...

    @property
    def incidents(self) -> IncidentRepository: ...

    @property
    def audits(self) -> AuditRepository: ...

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class OrderOpsService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self.uow_factory = uow_factory

    async def get_order(self, order_id: str) -> Order:
        async with self.uow_factory() as uow:
            normalized_id = order_id.strip()
            order = await uow.orders.get_by_id(normalized_id)
            if order is None:
                raise OrderNotFoundError(normalized_id)
            return order

    async def get_customer(self, customer_id: str) -> Customer:
        async with self.uow_factory() as uow:
            normalized_id = customer_id.strip()
            customer = await uow.customers.get_by_id(normalized_id)
            if customer is None:
                raise CustomerNotFoundError(normalized_id)
            return customer

    async def get_delivery_status(self, order_id: str) -> Delivery:
        async with self.uow_factory() as uow:
            normalized_id = order_id.strip()
            delivery = await uow.deliveries.get_by_order(normalized_id)
            if delivery is None:
                raise DeliveryNotFoundError(normalized_id)
            return delivery

    async def check_stock(self, product_id: str) -> ProductStock:
        async with self.uow_factory() as uow:
            normalized_id = product_id.strip()
            stock = await uow.inventory.get_by_product(normalized_id)
            if stock is None:
                raise ProductNotFoundError(normalized_id)
            return stock

    async def create_incident(
        self,
        command: CreateIncidentCommand,
        *,
        actor: str,
        proposed_by: str | None = None,
    ) -> IncidentCreationResult:
        async with self.uow_factory() as uow:
            order = await uow.orders.get_by_id(command.order_id)
            if order is None:
                raise OrderNotFoundError(command.order_id)

            if order.status == OrderStatus.CANCELLED:
                raise IncidentNotAllowedError(
                    "Impossible de créer un incident pour une commande annulée."
                )

            incident, created, stored_hash = await uow.incidents.create_or_get(command)
            if stored_hash != command.request_hash():
                raise IdempotencyConflictError(
                    "Cette clé d'idempotence a déjà été utilisée avec d'autres paramètres."
                )

            await uow.audits.add(
                action="create_incident",
                entity_type="incident",
                entity_id=incident.incident_id,
                actor=actor,
                outcome="created" if created else "already_existed",
                details={
                    "order_id": command.order_id,
                    "idempotency_key": command.idempotency_key,
                    **({"proposed_by": proposed_by} if proposed_by is not None else {}),
                },
            )
            await uow.commit()

            return IncidentCreationResult(
                incident=incident,
                already_existed=not created,
            )

    async def create_authorized_incident(
        self, command: CreateIncidentCommand, *, user: AppUser, proposed_by: str | None
    ) -> IncidentCreationResult:
        if not user.can_approve:
            raise PermissionError("Un superviseur est requis pour créer cet incident.")
        return await self.create_incident(command, actor=str(user.user_id), proposed_by=proposed_by)
