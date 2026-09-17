import asyncio
import os
import socket
import sys

import pytest
from langchain_mcp_adapters.client import MultiServerMCPClient

from orderops.access import DEMO_READER_ID, trusted_mcp_headers
from orderops.config import get_settings

pytestmark = pytest.mark.integration


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def wait_until_listening(port: int, process: asyncio.subprocess.Process) -> None:
    for _ in range(100):
        if process.returncode is not None:
            raise RuntimeError(f"MCP server stopped with exit code {process.returncode}")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.05)
        else:
            writer.close()
            await writer.wait_closed()
            return
    raise TimeoutError("MCP server did not start")


async def test_http_transport_exposes_five_tools_and_reads_an_order() -> None:
    port = available_port()
    environment = os.environ.copy()
    environment.update({"MCP_HOST": "127.0.0.1", "MCP_PORT": str(port)})
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "orderops.mcp.server",
        env=environment,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await wait_until_listening(port, process)
        client = MultiServerMCPClient(
            {
                "orderops": {
                    "transport": "streamable_http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                    "headers": trusted_mcp_headers(
                        DEMO_READER_ID, get_settings().mcp_internal_token.get_secret_value()
                    ),
                }
            }
        )
        tools = await client.get_tools()
        assert {tool.name for tool in tools} == {
            "get_order",
            "get_customer",
            "get_delivery_status",
            "check_stock",
            "create_incident",
        }
        get_order = next(tool for tool in tools if tool.name == "get_order")
        assert "CMD-1042" in str(await get_order.ainvoke({"order_id": "CMD-1042"}))
    finally:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
