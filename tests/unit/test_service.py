from datetime import UTC, datetime

import pytest

from orderops.domain.enums import IncidentStatus, OrderStatus
from orderops.domain.exceptions import (
    IdempotencyConflictError,
    IncidentNotAllowedError,
    OrderNotFoundError,
)
from orderops.domain.models import CreateIncidentCommand, Incident, Order
from orderops.services.orderops_service import OrderOpsService


class FakeOrderRepository:
    def __init__(self, orders: dict[str, Order]) -> None:
        self.orders = orders

    async def get_by_id(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)


class FakeIncidentRepository:
    def __init__(self, incidents: dict[str, tuple[Incident, str]]) -> None:
        self.incidents = incidents
        self.pending: tuple[str, Incident, str] | None = None

    async def create_or_get(self, command: CreateIncidentCommand) -> tuple[Incident, bool, str]:
        existing = self.incidents.get(command.idempotency_key)
        if existing:
            return existing[0], False, existing[1]

        incident = Incident(
            incident_id=f"INC-{len(self.incidents) + 1:04d}",
            order_id=command.order_id,
            reason=command.reason,
            status=IncidentStatus.OPEN,
            idempotency_key=command.idempotency_key,
            created_at=datetime.now(UTC),
        )
        self.pending = (command.idempotency_key, incident, command.request_hash())
        return incident, True, command.request_hash()


class FakeAuditRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.pending: list[dict[str, object]] = []
        self.committed: list[dict[str, object]] = []

    async def add(self, **entry: object) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.pending.append(entry)


class EmptyRepository:
    async def get_by_id(self, identifier: str) -> None:
        return None

    async def get_by_order(self, identifier: str) -> None:
        return None

    async def get_by_product(self, identifier: str) -> None:
        return None


class FakeUnitOfWork:
    def __init__(
        self,
        orders: dict[str, Order],
        incidents: dict[str, tuple[Incident, str]],
        audits: FakeAuditRepository,
    ) -> None:
        self.orders = FakeOrderRepository(orders)
        self.incidents = FakeIncidentRepository(incidents)
        self.audits = audits
        self.customers = EmptyRepository()
        self.inventory = EmptyRepository()
        self.deliveries = EmptyRepository()
        self.committed = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self.committed:
            self.incidents.pending = None
            self.audits.pending.clear()

    async def commit(self) -> None:
        if self.incidents.pending:
            key, incident, request_hash = self.incidents.pending
            self.incidents.incidents[key] = (incident, request_hash)
            self.incidents.pending = None
        self.audits.committed.extend(self.audits.pending)
        self.audits.pending.clear()
        self.committed = True


def make_order(status: OrderStatus = OrderStatus.SHIPPED) -> Order:
    return Order(
        order_id="CMD-1042",
        customer_id="CUS-001",
        status=status,
        created_at=datetime.now(UTC),
    )


def make_command(reason: str = "Retard confirmé") -> CreateIncidentCommand:
    return CreateIncidentCommand(
        order_id="CMD-1042",
        reason=reason,
        idempotency_key="unit-test-CMD-1042",
    )


async def test_get_order_normalizes_identifier_and_returns_order() -> None:
    orders = {"CMD-1042": make_order()}
    service = OrderOpsService(lambda: FakeUnitOfWork(orders, {}, FakeAuditRepository()))
    assert (await service.get_order(" CMD-1042 ")).order_id == "CMD-1042"


async def test_get_order_raises_for_unknown_order() -> None:
    service = OrderOpsService(lambda: FakeUnitOfWork({}, {}, FakeAuditRepository()))
    with pytest.raises(OrderNotFoundError):
        await service.get_order("CMD-4040")


async def test_create_incident_is_idempotent_and_audited() -> None:
    incidents: dict[str, tuple[Incident, str]] = {}
    audits = FakeAuditRepository()
    service = OrderOpsService(lambda: FakeUnitOfWork({"CMD-1042": make_order()}, incidents, audits))

    first = await service.create_incident(make_command(), actor="operator")
    second = await service.create_incident(make_command(), actor="operator-retry")

    assert first.already_existed is False
    assert second.already_existed is True
    assert first.incident.incident_id == second.incident.incident_id
    assert len(incidents) == 1
    assert [entry["outcome"] for entry in audits.committed] == [
        "created",
        "already_existed",
    ]


async def test_idempotency_key_with_different_payload_is_rejected() -> None:
    incidents: dict[str, tuple[Incident, str]] = {}
    service = OrderOpsService(
        lambda: FakeUnitOfWork({"CMD-1042": make_order()}, incidents, FakeAuditRepository())
    )
    await service.create_incident(make_command(), actor="operator")

    with pytest.raises(IdempotencyConflictError):
        await service.create_incident(make_command("Autre anomalie"), actor="operator")


async def test_incident_and_audit_are_atomic() -> None:
    incidents: dict[str, tuple[Incident, str]] = {}
    service = OrderOpsService(
        lambda: FakeUnitOfWork(
            {"CMD-1042": make_order()}, incidents, FakeAuditRepository(fail=True)
        )
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.create_incident(make_command(), actor="operator")
    assert incidents == {}


async def test_cancelled_order_rejects_incident() -> None:
    service = OrderOpsService(
        lambda: FakeUnitOfWork(
            {"CMD-1042": make_order(OrderStatus.CANCELLED)},
            {},
            FakeAuditRepository(),
        )
    )
    with pytest.raises(IncidentNotAllowedError):
        await service.create_incident(make_command(), actor="operator")
