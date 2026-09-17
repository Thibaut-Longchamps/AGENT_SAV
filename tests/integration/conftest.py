import asyncio
import os
import socket
import sys
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from orderops.config import get_settings


@pytest.fixture(scope="session", autouse=True)
def prepared_test_database() -> None:
    """Seed only an explicitly named test database; never mutate the development DB."""
    database_url = get_settings().database_url
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        pytest.skip("integration tests require a database whose name ends with '_test'")

    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(Path("scripts/seed.sql").read_text(encoding="utf-8"))
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")


@pytest.fixture
async def mcp_server_url():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
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
        for _ in range(200):
            if process.returncode is not None:
                raise RuntimeError(f"MCP exited with code {process.returncode}")
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                await asyncio.sleep(0.1)
            else:
                writer.close()
                await writer.wait_closed()
                break
        else:
            raise TimeoutError("MCP test server did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
