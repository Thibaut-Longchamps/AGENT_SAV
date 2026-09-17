from uuid import uuid4

import pytest
from sqlalchemy import func, select

from orderops.db.models import ActionAuditRow, IncidentRow
from orderops.db.session import SessionFactory
from orderops.domain.enums import DeliveryStatus
from orderops.domain.exceptions import IdempotencyConflictError
from orderops.domain.models import CreateIncidentCommand
from orderops.repositories.unit_of_work import SqlAlchemyUnitOfWork
from orderops.services.orderops_service import OrderOpsService

pytestmark = pytest.mark.integration


async def test_service_reads_seeded_order_stock_and_delivery() -> None:
    service = OrderOpsService(SqlAlchemyUnitOfWork)
    order = await service.get_order("CMD-1042")
    stock = await service.check_stock("SKU-12")
    delivery = await service.get_delivery_status("CMD-1042")

    assert order.order_id == "CMD-1042"
    assert {item.product_id for item in order.items} == {"SKU-12", "SKU-13"}
    assert stock.quantity_available == 16
    assert delivery.status == DeliveryStatus.DELAYED


async def test_incident_creation_is_idempotent_and_audited() -> None:
    service = OrderOpsService(SqlAlchemyUnitOfWork)
    key = f"integration-{uuid4()}"
    command = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Retard confirmé pendant le test d'intégration",
        idempotency_key=key,
    )

    first = await service.create_incident(command, actor="integration-test")
    second = await service.create_incident(command, actor="integration-retry")
    assert first.already_existed is False
    assert second.already_existed is True
    assert first.incident.incident_id == second.incident.incident_id

    async with SessionFactory() as session:
        incident_count = await session.scalar(
            select(func.count()).select_from(IncidentRow).where(IncidentRow.idempotency_key == key)
        )
        audit_count = await session.scalar(
            select(func.count())
            .select_from(ActionAuditRow)
            .where(ActionAuditRow.entity_id == first.incident.incident_id)
        )
    assert incident_count == 1
    assert audit_count == 2


async def test_reusing_key_with_different_payload_conflicts() -> None:
    service = OrderOpsService(SqlAlchemyUnitOfWork)
    key = f"integration-{uuid4()}"
    first = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Premier motif du test",
        idempotency_key=key,
    )
    second = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Second motif incompatible",
        idempotency_key=key,
    )
    await service.create_incident(first, actor="integration-test")
    with pytest.raises(IdempotencyConflictError):
        await service.create_incident(second, actor="integration-test")


class FailingAuditRepository:
    async def add(self, **entry: object) -> None:
        raise RuntimeError("forced audit failure")


class FailingAuditUnitOfWork(SqlAlchemyUnitOfWork):
    async def __aenter__(self) -> "FailingAuditUnitOfWork":
        await super().__aenter__()
        self.audits = FailingAuditRepository()  # type: ignore[assignment]
        return self


async def test_incident_rolls_back_when_audit_fails() -> None:
    key = f"integration-rollback-{uuid4()}"
    command = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Incident qui doit être annulé",
        idempotency_key=key,
    )
    service = OrderOpsService(FailingAuditUnitOfWork)
    with pytest.raises(RuntimeError, match="forced audit failure"):
        await service.create_incident(command, actor="integration-test")

    async with SessionFactory() as session:
        count = await session.scalar(
            select(func.count()).select_from(IncidentRow).where(IncidentRow.idempotency_key == key)
        )
    assert count == 0
