from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from orderops.access import DEMO_OPERATOR_ID, DEMO_READER_ID, DEMO_SUPERVISOR_ID, Role
from orderops.api.main import app
from tests.support.model import ScriptedToolCallingModel


def client(user_id=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Demo-User-Id": str(user_id)} if user_id else {},
    )


async def create_chat(api):
    response = await api.post("/conversations", json={"title": "Test sauvegarde"})
    assert response.status_code == 201
    return response.json()["thread_id"]


@pytest.mark.parametrize("message", ["CMD-1042", "Prépare un incident"])
async def test_owner_can_delete_chat_and_all_execution_state(demo_api_state, message):
    async with client(DEMO_OPERATOR_ID) as api:
        key = await create_chat(api)
        await api.post("/chat", json={"thread_id": key, "message": message})
        writer = demo_api_state.agents[Role.OPERATOR]
        assert key in writer.states
        response = await api.delete(f"/conversations/{key}")
        assert response.status_code == 204
        assert response.content == b""
        assert key not in writer.states
        assert not (await api.get("/conversations")).json()
        assert (await api.get(f"/conversations/{key}")).status_code == 404
        assert (await api.delete(f"/conversations/{key}")).status_code == 404
        assert (
            await api.post("/chat", json={"thread_id": key, "message": "reprendre"})
        ).status_code == 404
    async with client(DEMO_SUPERVISOR_ID) as supervisor:
        assert not (await supervisor.get("/approvals")).json()
        assert (
            await supervisor.post(f"/threads/{key}/decision", json={"decision": "approve"})
        ).status_code == 404
    assert writer.executions == 0


async def test_other_profiles_cannot_delete_even_a_visible_pending_chat(demo_api_state):
    async with client(DEMO_OPERATOR_ID) as owner:
        key = await create_chat(owner)
        await owner.post("/chat", json={"thread_id": key, "message": "Prépare un incident"})
    async with client(DEMO_SUPERVISOR_ID) as supervisor:
        assert (await supervisor.delete(f"/conversations/{key}")).status_code == 403
    async with client(DEMO_READER_ID) as reader:
        assert (await reader.delete(f"/conversations/{key}")).status_code == 404
    async with client() as anonymous:
        assert (await anonymous.delete(f"/conversations/{key}")).status_code == 401
    assert key in demo_api_state.agents[Role.OPERATOR].states


async def test_checkpoint_failure_does_not_remove_conversation(demo_api_state, monkeypatch):
    async def fail_delete(key):
        raise RuntimeError("Checkpoint indisponible")

    monkeypatch.setattr(demo_api_state.agents[Role.READER], "adelete_thread", fail_delete)
    async with client(DEMO_READER_ID) as api:
        key = await create_chat(api)
        with pytest.raises(RuntimeError, match="Checkpoint indisponible"):
            await api.delete(f"/conversations/{key}")
        assert (await api.get(f"/conversations/{key}")).status_code == 200


async def test_metadata_failure_can_be_retried_after_checkpoint_deletion(
    demo_api_state, monkeypatch
):
    delete = demo_api_state.store.delete

    async def fail_delete(key):
        raise RuntimeError("Métadonnées indisponibles")

    async with client(DEMO_READER_ID) as api:
        key = await create_chat(api)
        await api.post("/chat", json={"thread_id": key, "message": "CMD-1042"})
        monkeypatch.setattr(demo_api_state.store, "delete", fail_delete)
        with pytest.raises(RuntimeError, match="Métadonnées indisponibles"):
            await api.delete(f"/conversations/{key}")
        assert key not in demo_api_state.agents[Role.READER].states
        assert (await api.get(f"/conversations/{key}")).status_code == 200
        monkeypatch.setattr(demo_api_state.store, "delete", delete)
        assert (await api.delete(f"/conversations/{key}")).status_code == 204


async def test_deletion_clears_real_langgraph_checkpoints_and_preserves_other_chat(
    demo_api_state, monkeypatch
):
    saver = InMemorySaver()
    agent = create_agent(
        model=ScriptedToolCallingModel(responses=[AIMessage(content="Réponse locale")]),
        tools=[],
        checkpointer=saver,
    )
    monkeypatch.setitem(demo_api_state.agents, Role.READER, agent)
    async with client(DEMO_READER_ID) as api:
        key, other = await create_chat(api), await create_chat(api)
        for thread in (key, other):
            assert (
                await api.post("/chat", json={"thread_id": thread, "message": "Bonjour"})
            ).status_code == 200
        config = {"configurable": {"thread_id": key}}
        assert await saver.aget_tuple(config) is not None
        assert (await api.delete(f"/conversations/{key}")).status_code == 204
        assert await saver.aget_tuple(config) is None
        assert not [checkpoint async for checkpoint in saver.alist(config)]
        assert (await api.get(f"/conversations/{other}")).json()["messages"]


async def test_identity_required_and_inactive_user_rejected(demo_api_state):
    async with client() as api:
        assert (await api.get("/conversations")).status_code == 401
        assert (await api.get("/health")).status_code == 200
    demo_api_state.store.users[DEMO_READER_ID] = replace(
        demo_api_state.store.users[DEMO_READER_ID], active=False
    )
    async with client(DEMO_READER_ID) as api:
        assert (await api.get("/conversations")).status_code == 401


async def test_personal_history_is_restored_and_not_visible_to_other_users(demo_api_state):
    async with client(DEMO_READER_ID) as api:
        key = await create_chat(api)
        response = await api.post("/chat", json={"thread_id": key, "message": "CMD-1042"})
        assert response.status_code == 200
    async with client(DEMO_READER_ID) as reopened:
        assert len((await reopened.get("/conversations")).json()) == 1
        history = (await reopened.get(f"/conversations/{key}")).json()
        assert [message["content"] for message in history["messages"]] == [
            "CMD-1042",
            "Réponse sauvegardée.",
        ]
    for user_id in (DEMO_OPERATOR_ID, DEMO_SUPERVISOR_ID):
        async with client(user_id) as other:
            assert (await other.get(f"/conversations/{key}")).status_code == 404
            assert (
                await other.post("/chat", json={"thread_id": key, "message": "intrusion"})
            ).status_code == 404


@pytest.mark.parametrize("user_id", [DEMO_READER_ID, DEMO_OPERATOR_ID])
async def test_only_supervisor_can_decide_or_list_approvals(demo_api_state, user_id):
    async with client(user_id) as api:
        key = await create_chat(api)
        assert (
            await api.post(f"/threads/{key}/decision", json={"decision": "approve"})
        ).status_code == 403
        assert (await api.get("/approvals")).status_code == 403
    assert demo_api_state.agents[Role.OPERATOR].executions == 0


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_operator_proposes_supervisor_decides_without_replay(demo_api_state, decision):
    async with client(DEMO_OPERATOR_ID) as operator:
        key = await create_chat(operator)
        response = await operator.post(
            "/chat", json={"thread_id": key, "message": "Prépare un incident"}
        )
        assert response.json()["status"] == "approval_required"
        assert (
            await operator.post("/chat", json={"thread_id": key, "message": "autre"})
        ).status_code == 409
    writer = demo_api_state.agents[Role.OPERATOR]
    assert writer.executions == 0
    async with client(DEMO_SUPERVISOR_ID) as supervisor:
        assert len((await supervisor.get("/approvals")).json()) == 1
        history = (await supervisor.get(f"/conversations/{key}")).json()
        assert history["can_decide"] and not history["can_chat"]
        assert (
            await supervisor.post("/chat", json={"thread_id": key, "message": "intrusion"})
        ).status_code == 403
        result = await supervisor.post(f"/threads/{key}/decision", json={"decision": decision})
        assert result.status_code == 200
        assert (
            await supervisor.post(f"/threads/{key}/decision", json={"decision": decision})
        ).status_code == 409
        assert not (await supervisor.get("/approvals")).json()
        assert (await supervisor.get(f"/conversations/{key}")).status_code == 200
    assert writer.executions == (1 if decision == "approve" else 0)
    assert writer.calls[-1]["configurable"]["user_id"] == str(DEMO_SUPERVISOR_ID)
    assert writer.calls[-1]["configurable"]["approved"] == (decision == "approve")


async def test_client_cannot_choose_role_or_adopt_an_existing_checkpoint(demo_api_state):
    async with client(DEMO_READER_ID) as reader:
        key = await create_chat(reader)
        await reader.post(
            "/chat",
            json={"thread_id": key, "message": "CMD-1042", "role": "supervisor", "approved": True},
        )
        assert demo_api_state.agents[Role.READER].calls
        assert not demo_api_state.agents[Role.OPERATOR].calls
        assert (
            await reader.post("/chat", json={"thread_id": str(uuid4()), "message": "adoption"})
        ).status_code == 404
