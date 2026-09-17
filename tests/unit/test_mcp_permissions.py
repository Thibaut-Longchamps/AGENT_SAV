from types import SimpleNamespace
from uuid import uuid4

import pytest

from orderops.access import (
    DEMO_OPERATOR_ID,
    DEMO_READER_ID,
    DEMO_SUPERVISOR_ID,
    AppUser,
    Conversation,
    Role,
    trusted_mcp_headers,
)
from orderops.config import get_settings
from orderops.domain.models import CreateIncidentCommand
from orderops.mcp import authorization
from orderops.services.orderops_service import OrderOpsService

ARGS = {"order_id": "CMD-1042", "reason": "Retard", "idempotency_key": "permissions-test"}


def context(headers):
    return SimpleNamespace(
        request_context=SimpleNamespace(request=SimpleNamespace(headers=headers))
    )


def headers(user_id, thread_id="", approved=False):
    return trusted_mcp_headers(
        user_id,
        get_settings().mcp_internal_token.get_secret_value(),
        thread_id=thread_id,
        approved=approved,
    )


@pytest.fixture
def authorized_store(demo_api_state, monkeypatch):
    monkeypatch.setattr(authorization, "ConversationStore", lambda: demo_api_state.store)
    return demo_api_state.store


async def test_missing_internal_identity_is_rejected(authorized_store):
    with pytest.raises(PermissionError):
        await authorization.authorize_mcp_call(context({}))


@pytest.mark.parametrize("user_id", [DEMO_READER_ID, DEMO_OPERATOR_ID])
async def test_reader_and_operator_cannot_execute_writes_even_with_approval_header(
    authorized_store,
    user_id,
):
    with pytest.raises(PermissionError):
        await authorization.authorize_mcp_call(
            context(headers(user_id, approved=True)), arguments=ARGS
        )


async def test_all_active_profiles_can_read(authorized_store):
    for user_id in (DEMO_READER_ID, DEMO_OPERATOR_ID, DEMO_SUPERVISOR_ID):
        user, proposer = await authorization.authorize_mcp_call(context(headers(user_id)))
        assert user.user_id == user_id and proposer is None


async def test_only_exact_pending_proposal_can_be_executed(authorized_store):
    key = uuid4()
    authorized_store.chats[key] = Conversation(
        key,
        DEMO_OPERATOR_ID,
        "Opérateur",
        Role.OPERATOR,
        "Incident",
        "approval_required",
        [{"action_requests": [{"name": "create_incident", "args": ARGS}]}],
    )
    ctx = context(headers(DEMO_SUPERVISOR_ID, str(key), True))
    user, proposer = await authorization.authorize_mcp_call(ctx, arguments=ARGS)
    assert user.can_approve and proposer == str(DEMO_OPERATOR_ID)
    with pytest.raises(PermissionError):
        await authorization.authorize_mcp_call(ctx, arguments={**ARGS, "reason": "altéré"})
    with pytest.raises(PermissionError):
        await authorization.authorize_mcp_call(
            context(headers(DEMO_SUPERVISOR_ID, str(key), False)),
            arguments=ARGS,
        )


async def test_business_service_also_rejects_reader_and_operator():
    def forbidden_uow():
        raise AssertionError("No SQL session should be opened")

    service = OrderOpsService(forbidden_uow)
    for user_id, role in ((DEMO_READER_ID, Role.READER), (DEMO_OPERATOR_ID, Role.OPERATOR)):
        with pytest.raises(PermissionError):
            await service.create_authorized_incident(
                CreateIncidentCommand(**ARGS),
                user=AppUser(user_id, "Test", role),
                proposed_by=str(user_id),
            )
