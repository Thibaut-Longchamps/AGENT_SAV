import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection

from orderops.config import get_settings

pytestmark = pytest.mark.integration


async def test_checkpointer_schema_can_be_initialized() -> None:
    settings = get_settings()
    async with AsyncPostgresSaver.from_conn_string(
        settings.checkpoint_database_url
    ) as checkpointer:
        await checkpointer.setup()

    async with await AsyncConnection.connect(settings.checkpoint_database_url) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT to_regclass('public.checkpoints'), to_regclass('public.checkpoint_writes')"
            )
            checkpoints, checkpoint_writes = await cursor.fetchone() or (None, None)
    assert checkpoints == "checkpoints"
    assert checkpoint_writes == "checkpoint_writes"
