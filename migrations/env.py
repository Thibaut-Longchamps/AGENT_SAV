# Ce fichier configure Alembic pour le projet OrderOps.
#
# Son rôle est de faire le lien entre :
# - la configuration PostgreSQL de l'application ;
# - les modèles ORM SQLAlchemy définis dans db/models.py ;
# - Alembic, qui compare ces modèles avec l'état réel de la base.
#
# Base.metadata contient la description de toutes les tables ORM.
# L'import de models enregistre
# CustomerRow, OrderRow, IncidentRow, etc. dans Base.metadata.
#
# Alembic peut ensuite :
# 1. détecter les différences entre les modèles Python et PostgreSQL ;
# 2. générer automatiquement une migration ;
# 3. appliquer cette migration à la base.
#
# compare_type=True :
# détecte les changements de type, par exemple String → Text.
#
# compare_server_default=True :
# détecte les changements de valeurs par défaut côté PostgreSQL.
#
# La configuration est asynchrone car OrderOps utilise SQLAlchemy async.


from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import orderops.db.models as _models  # noqa: F401
from orderops.config import get_settings
from orderops.db.base import Base

# ------------------------------------------------------------
# Configuration générale Alembic
# ------------------------------------------------------------

# Récupère l'objet de configuration créé à partir de alembic.ini.
config = context.config


# Configure les logs Alembic si un fichier de configuration est présent.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Configuration issue des variables du processus et du fichier .env.
settings = get_settings()


# Donne à Alembic l'URL PostgreSQL utilisée par l'application.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)


# ------------------------------------------------------------
# Métadonnées SQLAlchemy
# ------------------------------------------------------------

# Base.metadata contient la description de toutes les tables ORM.
#
# L'import suivant effectué plus haut :
#
# from orderops.db import models as _models
#
# provoque le chargement de toutes les classes héritant de Base.
#
# Elles sont donc enregistrées dans Base.metadata.
target_metadata = Base.metadata

# Ces tables appartiennent à langchain-postgres et au checkpointer LangGraph.
# Elles sont créées et mises à jour par leurs bibliothèques respectives, pas par
# les modèles ORM métier ni par l'autogénération Alembic d'OrderOps.
EXTERNALLY_MANAGED_TABLE_PREFIXES = ("langchain_pg_", "checkpoint")


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    if type_ == "table" and name is not None:
        return not name.startswith(EXTERNALLY_MANAGED_TABLE_PREFIXES)
    return True


# ------------------------------------------------------------
# Mode OFFLINE
# ------------------------------------------------------------


def run_migrations_offline() -> None:
    """
    Exécute les scripts de migration en mode offline,
    sans ouvrir de connexion à PostgreSQL.

    Au lieu de modifier la base, Alembic produit le SQL
    correspondant aux migrations.
    """

    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        # Génère les valeurs directement dans le SQL produit.
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        # Détecte les modifications de types SQL.
        compare_type=True,
        # Détecte les modifications des valeurs par défaut PostgreSQL.
        compare_server_default=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


# ------------------------------------------------------------
# Exécution d'une migration sur une connexion
# ------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """
    Configure Alembic avec une connexion PostgreSQL ouverte
    puis exécute les migrations.
    """

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


# ------------------------------------------------------------
# Mode ONLINE asynchrone
# ------------------------------------------------------------


async def run_async_migrations() -> None:
    """
    Crée une connexion SQLAlchemy asynchrone vers PostgreSQL
    puis exécute Alembic dessus.
    """

    connectable = async_engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        # Préfixe des paramètres SQLAlchemy dans alembic.ini.
        prefix="sqlalchemy.",
        # Alembic n'a pas besoin de conserver un pool
        # permanent de connexions.
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # run_sync exécute la fonction de migration synchrone sur la connexion async.
        await connection.run_sync(do_run_migrations)

    # Libère les ressources du moteur après la migration.
    await connectable.dispose()


# ------------------------------------------------------------
# Choix du mode d'exécution
# ------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()

else:
    import asyncio

    asyncio.run(run_async_migrations())
