from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orderops.db.session import SessionFactory
from orderops.repositories.sqlalchemy import (
    SqlAlchemyAuditRepository,
    SqlAlchemyCustomerRepository,
    SqlAlchemyDeliveryRepository,
    SqlAlchemyIncidentRepository,
    SqlAlchemyInventoryRepository,
    SqlAlchemyOrderRepository,
)


class SqlAlchemyUnitOfWork:
    """Own one SQLAlchemy session and its transaction boundary."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession]
        | Callable[[], AsyncSession] = SessionFactory,
    ) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.orders = SqlAlchemyOrderRepository(self.session)
        self.customers = SqlAlchemyCustomerRepository(self.session)
        self.inventory = SqlAlchemyInventoryRepository(self.session)
        self.deliveries = SqlAlchemyDeliveryRepository(self.session)
        self.incidents = SqlAlchemyIncidentRepository(self.session)
        self.audits = SqlAlchemyAuditRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self.session.in_transaction():
                await self.session.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
