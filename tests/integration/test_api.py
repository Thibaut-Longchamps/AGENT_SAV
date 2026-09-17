import pytest
from httpx import ASGITransport, AsyncClient
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from orderops.access import DEMO_READER_ID, Role
from orderops.api.main import app
from orderops.repositories.conversations import ConversationStore
from tests.support.model import ScriptedToolCallingModel

pytestmark = pytest.mark.integration


async def test_health_chat_and_history_routes_without_live_model(monkeypatch) -> None:
    agent = create_agent(
        model=ScriptedToolCallingModel(responses=[AIMessage(content="Réponse déterministe")]),
        tools=[],
        checkpointer=InMemorySaver(),
    )
    monkeypatch.setattr(app.state, "agents", {Role.READER: agent}, raising=False)
    monkeypatch.setattr(app.state, "conversations", ConversationStore(), raising=False)
    monkeypatch.setattr(app.state, "thread_locks", {}, raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Demo-User-Id": str(DEMO_READER_ID)},
    ) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        created = await client.post("/conversations", json={"title": "Intégration API"})
        assert created.status_code == 201
        thread_id = created.json()["thread_id"]
        chat_response = await client.post(
            "/chat",
            json={"thread_id": thread_id, "message": "Où est CMD-1042 ?"},
        )
        history = await client.get(f"/conversations/{thread_id}")
        decision_response = await client.post(
            f"/threads/{thread_id}/decision",
            json={"decision": "reject", "message": "Refus de test"},
        )

    assert chat_response.status_code == 200
    assert chat_response.json()["answer"] == "Réponse déterministe"
    assert history.json()["messages"][-1]["content"] == "Réponse déterministe"
    assert decision_response.status_code == 403
