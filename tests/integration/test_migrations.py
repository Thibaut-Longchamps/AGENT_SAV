import os
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

from orderops.config import get_settings

pytestmark = pytest.mark.integration


def test_migrations_support_upgrade_downgrade_upgrade_cycle() -> None:
    original_database_url = get_settings().database_url
    original_url = make_url(original_database_url)
    temporary_database = f"orderops_migration_test_{uuid4().hex[:12]}"
    admin_dsn = original_database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(admin_dsn, autocommit=True) as admin_connection:
        admin_connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(temporary_database))
        )

    temporary_url = original_url.set(database=temporary_database).render_as_string(
        hide_password=False
    )
    previous_environment_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = temporary_url
    alembic_config = Config("alembic.ini")

    try:
        get_settings.cache_clear()
        command.upgrade(alembic_config, "head")
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")

        dsn = temporary_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(dsn) as connection:
            tables = connection.execute(
                "SELECT to_regclass('public.orders'), to_regclass('public.incidents')"
            ).fetchone()
            extension = connection.execute(
                "SELECT extname FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
        assert tables == ("orders", "incidents")
        assert extension == ("vector",)
    finally:
        if previous_environment_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_environment_url
        get_settings.cache_clear()

        with psycopg.connect(admin_dsn, autocommit=True) as admin_connection:
            admin_connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (temporary_database,),
            )
            admin_connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(temporary_database))
            )
