import asyncio

from orderops.domain.models import CreateIncidentCommand
from orderops.repositories.unit_of_work import SqlAlchemyUnitOfWork
from orderops.services.orderops_service import OrderOpsService


async def main() -> None:
    service = OrderOpsService(SqlAlchemyUnitOfWork)
    print((await service.get_order("CMD-1042")).model_dump(mode="json"))

    command = CreateIncidentCommand(
        order_id="CMD-1042",
        reason="Retard confirmé par le transporteur",
        idempotency_key="demo-CMD-1042-delay",
    )
    first = await service.create_incident(command, actor="smoke-test")
    second = await service.create_incident(command, actor="smoke-test-retry")
    print(first.model_dump(mode="json"))
    print(second.model_dump(mode="json"))


if __name__ == "__main__":
    asyncio.run(main())
