"""Demo identities and deterministic permissions; not an authentication system."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    READER = "reader"
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"


DEMO_READER_ID = UUID("00000000-0000-0000-0000-000000000001")
DEMO_OPERATOR_ID = UUID("00000000-0000-0000-0000-000000000002")
DEMO_SUPERVISOR_ID = UUID("00000000-0000-0000-0000-000000000003")


@dataclass(frozen=True)
class AppUser:
    user_id: UUID
    name: str
    role: Role
    active: bool = True

    @property
    def can_propose(self) -> bool:
        return self.active and self.role in (Role.OPERATOR, Role.SUPERVISOR)

    @property
    def can_approve(self) -> bool:
        return self.active and self.role == Role.SUPERVISOR


@dataclass(frozen=True)
class Conversation:
    thread_id: UUID
    owner_id: UUID
    owner_name: str
    owner_role: Role
    title: str
    status: str
    pending_actions: list[dict]
    reviewer_id: UUID | None = None


def can_read_conversation(user: AppUser, conversation: Conversation) -> bool:
    if not user.active:
        return False
    if user.user_id == conversation.owner_id:
        return True
    return (
        user.can_approve
        and conversation.owner_role == Role.OPERATOR
        and (conversation.status == "approval_required" or conversation.reviewer_id == user.user_id)
    )


def can_decide(user: AppUser, conversation: Conversation) -> bool:
    return user.can_approve and can_read_conversation(user, conversation)


def trusted_mcp_headers(
    user_id: UUID, token: str, *, approved: bool = False, thread_id: str = ""
) -> dict[str, str]:
    """Only the server/client code supplies these headers, never tool arguments."""
    return {
        "x-orderops-internal-token": token,
        "x-orderops-user-id": str(user_id),
        "x-orderops-thread-id": thread_id,
        "x-orderops-approved": "true" if approved else "false",
    }
