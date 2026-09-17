import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from orderops.config import get_settings


async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(
        get_settings().checkpoint_database_url
    ) as checkpointer:
        await checkpointer.setup()


if __name__ == "__main__":
    asyncio.run(main())
