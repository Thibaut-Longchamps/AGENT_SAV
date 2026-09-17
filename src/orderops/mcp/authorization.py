import secrets
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import Context

from orderops.access import AppUser, can_decide
from orderops.config import get_settings
from orderops.repositories.conversations import ConversationStore


async def authorize_mcp_call(
    ctx: Context, *, arguments: dict[str, Any] | None = None
) -> tuple[AppUser, str | None]:
    """A role/approval never comes from the LLM tool schema.

    The internal token is only a local-demo trust boundary, not user authentication.
    """
    settings = get_settings()
    if not settings.demo_mode or settings.app_env == "production":
        raise PermissionError("Les identités simulées sont réservées à la démonstration locale.")
    request = ctx.request_context.request
    headers = getattr(request, "headers", {})
    token = settings.mcp_internal_token.get_secret_value()
    supplied = headers.get("x-orderops-internal-token", "")
    if not token or not secrets.compare_digest(supplied, token):
        raise PermissionError("Appel MCP interne non autorisé.")
    try:
        user_id = UUID(headers.get("x-orderops-user-id", ""))
    except ValueError as exc:
        raise PermissionError("Identité utilisateur MCP manquante.") from exc
    store = ConversationStore()
    user = await store.get_user(user_id)
    if user is None:
        raise PermissionError("Utilisateur inconnu ou désactivé.")
    if arguments is None:
        return user, None

    if not user.can_approve or headers.get("x-orderops-approved") != "true":
        raise PermissionError("Seul un superviseur peut exécuter une création approuvée.")
    try:
        thread_id = UUID(headers.get("x-orderops-thread-id", ""))
    except ValueError as exc:
        raise PermissionError("Conversation d'approbation manquante.") from exc
    conversation = await store.get(thread_id)
    if conversation is None or not can_decide(user, conversation):
        raise PermissionError("Conversation non autorisée pour une création.")
    allowed_actions = [
        action
        for interrupt in conversation.pending_actions
        for action in interrupt.get("action_requests", [])
        if action.get("name") == "create_incident"
    ]
    if conversation.status != "approval_required" or not any(
        action.get("args") == arguments for action in allowed_actions
    ):
        raise PermissionError("L'action ne correspond pas à la proposition en attente.")
    return user, str(conversation.owner_id)
