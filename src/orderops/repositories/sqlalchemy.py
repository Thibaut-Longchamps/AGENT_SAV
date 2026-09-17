from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orderops.db.models import (
    ActionAuditRow,
    CustomerRow,
    DeliveryRow,
    IncidentRow,
    InventoryRow,
    OrderRow,
    ProductRow,
)
from orderops.domain.enums import DeliveryStatus, IncidentStatus, OrderStatus
from orderops.domain.models import (
    CreateIncidentCommand,
    Customer,
    Delivery,
    Incident,
    Order,
    OrderItem,
    ProductStock,
)


class SqlAlchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: str) -> Order | None:
        result = await self.session.execute(
            select(OrderRow)
            .options(selectinload(OrderRow.items))
            .where(OrderRow.order_id == order_id)
        )
        row = result.scalar_one_or_none()

        if row is None:
            return None

        product_ids = [item.product_id for item in row.items]
        product_names: dict[str, str] = {}

        if product_ids:
            products = await self.session.execute(
                select(ProductRow).where(ProductRow.product_id.in_(product_ids))
            )
            product_names = {product.product_id: product.name for product in products.scalars()}

        return Order(
            order_id=row.order_id,
            customer_id=row.customer_id,
            status=OrderStatus(row.status),
            expected_delivery=row.expected_delivery,
            created_at=row.created_at,
            items=tuple(
                OrderItem(
                    product_id=item.product_id,
                    product_name=product_names[item.product_id],
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
                for item in row.items
            ),
        )


class SqlAlchemyCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, customer_id: str) -> Customer | None:
        row = await self.session.scalar(
            select(CustomerRow).where(CustomerRow.customer_id == customer_id)
        )

        if row is None:
            return None

        return Customer(
            customer_id=row.customer_id,
            name=row.name,
            email=row.email,
            phone=row.phone,
        )


class SqlAlchemyInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_product(
        self,
        product_id: str,
    ) -> ProductStock | None:
        result = await self.session.execute(
            select(InventoryRow, ProductRow)
            .join(
                ProductRow,
                ProductRow.product_id == InventoryRow.product_id,
            )
            .where(InventoryRow.product_id == product_id)
        )
        record = result.one_or_none()

        if record is None:
            return None

        inventory, product = record
        available = inventory.on_hand_quantity - inventory.reserved_quantity

        return ProductStock(
            product_id=product.product_id,
            product_name=product.name,
            on_hand_quantity=inventory.on_hand_quantity,
            reserved_quantity=inventory.reserved_quantity,
            quantity_available=available,
        )


class SqlAlchemyDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_order(self, order_id: str) -> Delivery | None:
        row = await self.session.scalar(select(DeliveryRow).where(DeliveryRow.order_id == order_id))

        if row is None:
            return None

        return Delivery(
            delivery_id=row.delivery_id,
            order_id=row.order_id,
            status=DeliveryStatus(row.status),
            carrier=row.carrier,
            tracking_number=row.tracking_number,
            expected_delivery=row.expected_delivery,
        )


class SqlAlchemyIncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_or_get(
        self,
        command: CreateIncidentCommand,
    ) -> tuple[Incident, bool, str]:
        candidate_id = f"INC-{uuid4().hex[:16].upper()}"
        request_hash = command.request_hash()

        statement = (
            insert(IncidentRow)
            .values(
                incident_id=candidate_id,
                order_id=command.order_id,
                reason=command.reason,
                status=IncidentStatus.OPEN.value,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
            )
            .on_conflict_do_nothing(index_elements=[IncidentRow.idempotency_key])
            .returning(IncidentRow.incident_id)
        )

        created_id = (await self.session.execute(statement)).scalar_one_or_none()

        row = await self.session.scalar(
            select(IncidentRow).where(IncidentRow.idempotency_key == command.idempotency_key)
        )
        assert row is not None

        incident = Incident(
            incident_id=row.incident_id,
            order_id=row.order_id,
            reason=row.reason,
            status=IncidentStatus(row.status),
            idempotency_key=row.idempotency_key,
            created_at=row.created_at,
        )

        return incident, created_id is not None, row.request_hash


class SqlAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        outcome: str,
        details: dict[str, object],
    ) -> None:
        self.session.add(
            ActionAuditRow(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                actor=actor,
                outcome=outcome,
                details=details,
            )
        )
        await self.session.flush()
