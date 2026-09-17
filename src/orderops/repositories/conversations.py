"""Metadata in PostgreSQL; the actual transcript remains in the LangGraph checkpointer."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select

from orderops.access import AppUser, Conversation, Role, can_read_conversation
from orderops.db.models import ConversationRow, UserRoleRow, UserRow
from orderops.db.session import SessionFactory


class ConversationStore:
    def __init__(self, session_factory: Any = SessionFactory) -> None:
        self.session_factory = session_factory

    async def list_users(self) -> list[AppUser]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserRow, UserRoleRow.role_id)
                .join(UserRoleRow, UserRoleRow.user_id == UserRow.user_id)
                .where(UserRow.active.is_(True))
                .order_by(UserRow.user_id)
            )
            return [
                AppUser(user.user_id, user.name, Role(role), user.active)
                for user, role in result.all()
            ]

    async def get_user(self, user_id: UUID) -> AppUser | None:
        # Le rôle et l'état actif sont relus en base à chaque appel.
        return next((user for user in await self.list_users() if user.user_id == user_id), None)

    async def create(self, user: AppUser, title: str) -> Conversation:
        async with self.session_factory() as session:
            row = ConversationRow(
                thread_id=uuid4(),
                owner_id=user.user_id,
                title=title,
                status="completed",
                pending_actions=[],
            )
            session.add(row)
            await session.commit()
            return Conversation(
                row.thread_id, user.user_id, user.name, user.role, row.title, row.status, []
            )

    async def delete(self, thread_id: UUID) -> None:
        async with self.session_factory() as session:
            row = await session.get(ConversationRow, thread_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    @staticmethod
    def _conversation(row: ConversationRow, owner: UserRow, role: str) -> Conversation:
        return Conversation(
            row.thread_id,
            row.owner_id,
            owner.name,
            Role(role),
            row.title,
            row.status,
            row.pending_actions,
            row.reviewer_id,
        )

    async def get(self, thread_id: UUID) -> Conversation | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ConversationRow, UserRow, UserRoleRow.role_id)
                .join(UserRow, UserRow.user_id == ConversationRow.owner_id)
                .join(UserRoleRow, UserRoleRow.user_id == UserRow.user_id)
                .where(ConversationRow.thread_id == thread_id)
            )
            item = result.first()
            return self._conversation(*item) if item else None

    async def list_visible(
        self, user: AppUser, *, pending_only: bool = False
    ) -> list[Conversation]:
        async with self.session_factory() as session:
            query = (
                select(ConversationRow, UserRow, UserRoleRow.role_id)
                .join(UserRow, UserRow.user_id == ConversationRow.owner_id)
                .join(UserRoleRow, UserRoleRow.user_id == UserRow.user_id)
                .order_by(ConversationRow.updated_at.desc(), ConversationRow.thread_id)
            )
            if pending_only:
                query = query.where(ConversationRow.status == "approval_required")
            else:
                query = query.where(
                    (ConversationRow.owner_id == user.user_id)
                    | (ConversationRow.reviewer_id == user.user_id)
                )
            result = await session.execute(query)
            conversations = [self._conversation(*item) for item in result.all()]
            return [
                conversation
                for conversation in conversations
                if can_read_conversation(user, conversation)
            ]

    async def save_state(
        self,
        thread_id: UUID,
        *,
        actions: list[dict[str, Any]],
        failed: bool = False,
        reviewer_id: UUID | None = None,
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(ConversationRow, thread_id)
            if row is None:
                raise ValueError("Conversation introuvable")
            row.pending_actions = actions
            row.status = "approval_required" if actions else ("error" if failed else "completed")
            row.updated_at = func.now()
            if reviewer_id is not None:
                row.reviewer_id = reviewer_id
            await session.commit()
