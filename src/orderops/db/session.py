# Moteur SQLAlchemy asynchrone, pool de connexions et fabrique de sessions PostgreSQL.
# Les repositories utilisent ces sessions pour leurs requêtes et transactions.

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from orderops.config import get_settings

# Configuration issue des variables du processus et du fichier .env.
settings = get_settings()


# ============================================================
# MOTEUR SQLALCHEMY
# ============================================================

# Le moteur représente le point d'entrée vers PostgreSQL.
#
# Il connaît notamment :
# - l'adresse de PostgreSQL ;
# - les identifiants ;
# - le nom de la base ;
# - la configuration du pool de connexions.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    # Vérifie qu'une connexion du pool fonctionne
    # avant de la réutiliser.
    pool_pre_ping=True,
    # Le pool conserve au plus cinq connexions entre les utilisations.
    pool_size=5,
    # Connexions supplémentaires autorisées temporairement.
    max_overflow=10,
)


# ============================================================
# FABRIQUE DE SESSIONS
# ============================================================

# SessionFactory crée les AsyncSession utilisées par les repositories.
#
# Une session représente une unité de travail avec PostgreSQL :
# SELECT, INSERT, UPDATE, DELETE, commit, rollback...
SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # Le commit n'expire pas les attributs déjà chargés des objets ORM.
    expire_on_commit=False,
    # Les requêtes ne déclenchent pas de flush implicite des modifications en attente.
    autoflush=False,
)


# ============================================================
# CRÉATION D'UNE SESSION
# ============================================================


async def get_session() -> AsyncIterator[AsyncSession]:
    """Fournit une session PostgreSQL puis la ferme automatiquement."""

    async with SessionFactory() as session:
        yield session


# ============================================================
# FERMETURE DU MOTEUR
# ============================================================


async def dispose_engine() -> None:
    """Ferme les connexions disponibles dans le pool PostgreSQL."""

    await engine.dispose()
