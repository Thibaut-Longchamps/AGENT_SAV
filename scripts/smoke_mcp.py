import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

from orderops.access import DEMO_READER_ID, trusted_mcp_headers
from orderops.config import get_settings


async def main() -> None:
    client = MultiServerMCPClient(
        {
            "orderops": {
                "transport": "streamable_http",
                "url": get_settings().mcp_url,
                "headers": trusted_mcp_headers(
                    DEMO_READER_ID, get_settings().mcp_internal_token.get_secret_value()
                ),
            }
        }
    )
    tools = await client.get_tools()
    print([tool.name for tool in tools])
    get_order = next(tool for tool in tools if tool.name == "get_order")
    print(await get_order.ainvoke({"order_id": "CMD-1042"}))


if __name__ == "__main__":
    asyncio.run(main())
