from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from orderops.config import get_settings
from orderops.domain.models import CreateIncidentCommand
from orderops.mcp.authorization import authorize_mcp_call
from orderops.repositories.unit_of_work import SqlAlchemyUnitOfWork
from orderops.services.orderops_service import OrderOpsService

settings = get_settings()
service = OrderOpsService(SqlAlchemyUnitOfWork)

mcp = FastMCP(
    "OrderOps Business Tools",
    host=settings.mcp_host,
    port=settings.mcp_port,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def get_order(order_id: str, ctx: Context) -> dict[str, Any]:
    """Retrieve an order and its lines. Read-only."""
    await authorize_mcp_call(ctx)
    return (await service.get_order(order_id)).model_dump(mode="json")


@mcp.tool()
async def get_customer(customer_id: str, ctx: Context) -> dict[str, Any]:
    """Retrieve customer information. Read-only."""
    await authorize_mcp_call(ctx)
    return (await service.get_customer(customer_id)).model_dump(mode="json")


@mcp.tool()
async def get_delivery_status(order_id: str, ctx: Context) -> dict[str, Any]:
    """Retrieve delivery tracking information. Read-only."""
    await authorize_mcp_call(ctx)
    return (await service.get_delivery_status(order_id)).model_dump(mode="json")


@mcp.tool()
async def check_stock(product_id: str, ctx: Context) -> dict[str, Any]:
    """Check available stock for one product. Read-only."""
    await authorize_mcp_call(ctx)
    return (await service.check_stock(product_id)).model_dump(mode="json")


@mcp.tool()
async def create_incident(
    order_id: str,
    reason: str,
    idempotency_key: str,
    ctx: Context,
) -> dict[str, Any]:
    """Create a logistics incident. This modifies business data."""
    user, proposer = await authorize_mcp_call(
        ctx,
        arguments={
            "order_id": order_id,
            "reason": reason,
            "idempotency_key": idempotency_key,
        },
    )
    command = CreateIncidentCommand(
        order_id=order_id,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    result = await service.create_authorized_incident(command, user=user, proposed_by=proposer)
    return result.model_dump(mode="json")


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
