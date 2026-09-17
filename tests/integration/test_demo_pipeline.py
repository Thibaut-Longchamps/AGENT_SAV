from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select

from orderops.access import (
    DEMO_OPERATOR_ID,
    DEMO_READER_ID,
    DEMO_SUPERVISOR_ID,
    Role,
    trusted_mcp_headers,
)
from orderops.agent import factory
from orderops.api.main import app
from orderops.config import get_settings
from orderops.db.models import ActionAuditRow, IncidentRow
from orderops.db.session import SessionFactory
from orderops.repositories.conversations import ConversationStore
from tests.support.model import ScriptedToolCallingModel

pytestmark = pytest.mark.integration


class ApprovedProcedureStore:
    async def asimilarity_search(self, query, *, k, filter):
        return [
            Document(
                page_content="Préparer un incident après validation du superviseur.",
                metadata={"source": "delivery_delay.md", "version": "1"},
            )
        ]


def tool_response(name, args):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": uuid4().hex,
                "type": "tool_call",
            }
        ],
    )


def api_client(user_id):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Demo-User-Id": str(user_id)},
    )


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_persisted_operator_chat_resumes_after_restart_with_supervisor(
    mcp_server_url,
    monkeypatch,
    decision,
):
    settings = get_settings().model_copy(update={"mcp_url": mcp_server_url})
    key = f"persisted-demo-{uuid4().hex}"
    responses = [
        tool_response("get_order", {"order_id": "CMD-1042"}),
        tool_response("search_procedures", {"query": "retard de livraison"}),
        tool_response(
            "create_incident",
            {"order_id": "CMD-1042", "reason": "Retard confirmé", "idempotency_key": key},
        ),
        AIMessage(content="Traitement terminé."),
    ]
    monkeypatch.setattr(
        factory, "ChatMistralAI", lambda **kwargs: ScriptedToolCallingModel(responses=responses)
    )
    monkeypatch.setattr(app.state, "conversations", ConversationStore(), raising=False)
    monkeypatch.setattr(app.state, "thread_locks", {}, raising=False)
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
        await saver.setup()
        agent, _ = await factory.build_agent(settings, saver, ApprovedProcedureStore())
        monkeypatch.setattr(app.state, "agents", {Role.OPERATOR: agent}, raising=False)
        async with api_client(DEMO_OPERATOR_ID) as operator:
            created = await operator.post("/conversations", json={"title": f"Reprise {key}"})
            assert created.status_code == 201
            thread_id = created.json()["thread_id"]
            result = await operator.post(
                "/chat", json={"thread_id": thread_id, "message": "Prépare un incident CMD-1042"}
            )
            assert result.status_code == 200
            assert result.json()["status"] == "approval_required"
            assert (
                await operator.post(f"/threads/{thread_id}/decision", json={"decision": decision})
            ).status_code == 403
            snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
            completed_tools = [
                message
                for message in snapshot.values["messages"]
                if isinstance(message, ToolMessage)
            ]
            assert {message.name for message in completed_tools} == {
                "get_order",
                "search_procedures",
            }
            assert all(message.status != "error" for message in completed_tools)

    # A fresh saver, graph, repository and API client simulate a backend/browser restart.
    responses = [AIMessage(content="Traitement terminé après reprise.")]
    monkeypatch.setattr(app.state, "conversations", ConversationStore())
    monkeypatch.setattr(app.state, "thread_locks", {})
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
        agent, _ = await factory.build_agent(settings, saver, ApprovedProcedureStore())
        monkeypatch.setattr(app.state, "agents", {Role.OPERATOR: agent})
        async with api_client(DEMO_SUPERVISOR_ID) as supervisor:
            pending = (await supervisor.get("/approvals")).json()
            assert any(item["thread_id"] == thread_id for item in pending)
            history = (await supervisor.get(f"/conversations/{thread_id}")).json()
            assert history["messages"][0]["content"] == "Prépare un incident CMD-1042"
            assert history["can_decide"] and history["actions"]
            result = await supervisor.post(
                f"/threads/{thread_id}/decision", json={"decision": decision}
            )
            assert result.status_code == 200
            assert result.json()["status"] == "completed"
            assert (
                await supervisor.post(f"/threads/{thread_id}/decision", json={"decision": decision})
            ).status_code == 409
        async with api_client(DEMO_OPERATOR_ID) as operator:
            history = (await operator.get(f"/conversations/{thread_id}")).json()
            assert history["messages"][-1]["content"] == "Traitement terminé après reprise."
            assert history["can_chat"] and not history["actions"]
        snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
        executed = [
            message
            for message in snapshot.values["messages"]
            if isinstance(message, ToolMessage) and message.name == "create_incident"
        ]
        if decision == "approve":
            assert len(executed) == 1 and executed[0].status != "error"

    async with SessionFactory() as session:
        incident = (
            await session.execute(select(IncidentRow).where(IncidentRow.idempotency_key == key))
        ).scalar_one_or_none()
        conversation = await ConversationStore().get(UUID(thread_id))
        assert conversation.reviewer_id == DEMO_SUPERVISOR_ID
        if decision == "approve":
            assert incident is not None
            audit = (
                (
                    await session.execute(
                        select(ActionAuditRow)
                        .where(ActionAuditRow.entity_id == incident.incident_id)
                        .order_by(ActionAuditRow.id.desc())
                    )
                )
                .scalars()
                .first()
            )
            assert audit.actor == str(DEMO_SUPERVISOR_ID)
            assert audit.details["proposed_by"] == str(DEMO_OPERATOR_ID)
        else:
            assert incident is None


async def test_reader_graph_hides_write_tool_and_direct_mcp_call_is_denied(
    mcp_server_url,
    monkeypatch,
):
    settings = get_settings().model_copy(update={"mcp_url": mcp_server_url})
    monkeypatch.setattr(
        factory,
        "ChatMistralAI",
        lambda **kwargs: ScriptedToolCallingModel(
            responses=[AIMessage(content="Lecture uniquement.")]
        ),
    )
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
        reader, client = await factory.build_agent(
            settings, saver, ApprovedProcedureStore(), role=Role.READER
        )
        # Model binding receives no create_incident tool for this graph.
        tool_node = reader.get_graph().nodes["tools"].data
        assert "create_incident" not in tool_node.tools_by_name
        assert "get_order" in tool_node.tools_by_name
        # Even retrieving all tools cannot bypass the interceptor's role check.
        tools = await client.get_tools()
        assert any(tool.name == "create_incident" for tool in tools)
        from types import SimpleNamespace

        async def forbidden_handler(request):
            raise AssertionError("The MCP transport must not be called")

        with pytest.raises(PermissionError, match="Tool interdit"):
            await client.tool_interceptors[0](
                MCPToolCallRequest(
                    name="create_incident",
                    args={},
                    server_name="orderops",
                    runtime=SimpleNamespace(
                        config={
                            "configurable": {
                                "user_id": str(DEMO_READER_ID),
                                "approved": True,
                            }
                        }
                    ),
                ),
                forbidden_handler,
            )


async def test_direct_mcp_transport_cannot_bypass_identity_or_pending_approval(mcp_server_url):
    settings = get_settings()
    for user_id in (None, DEMO_READER_ID, DEMO_OPERATOR_ID, DEMO_SUPERVISOR_ID):
        headers = (
            trusted_mcp_headers(
                user_id,
                settings.mcp_internal_token.get_secret_value(),
                approved=True,
                thread_id=str(uuid4()),
            )
            if user_id
            else {}
        )
        client = MultiServerMCPClient(
            {
                "orderops": {
                    "transport": "streamable_http",
                    "url": mcp_server_url,
                    "headers": headers,
                }
            }
        )
        tools = await client.get_tools()
        tool = next(tool for tool in tools if tool.name == "create_incident")
        key = f"direct-denied-{uuid4().hex}"
        response = await tool.ainvoke(
            {
                "name": "create_incident",
                "id": uuid4().hex,
                "type": "tool_call",
                "args": {
                    "order_id": "CMD-1042",
                    "reason": "Accès direct interdit",
                    "idempotency_key": key,
                },
            }
        )
        # MCP execution failures are returned to the model as error ToolMessages.
        assert isinstance(response, ToolMessage) and response.status == "error"
        async with SessionFactory() as session:
            assert (
                await session.execute(select(IncidentRow).where(IncidentRow.idempotency_key == key))
            ).scalar_one_or_none() is None
