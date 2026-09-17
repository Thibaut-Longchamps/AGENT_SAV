import asyncio
from typing import Any
from uuid import uuid4

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from orderops.agent.factory import human_in_the_loop_middleware
from tests.support.model import ScriptedToolCallingModel


def build_deterministic_agent(executions: list[dict[str, str]]) -> Any:
    @tool
    async def create_incident(order_id: str, reason: str, idempotency_key: str) -> str:
        """Create a test incident after human approval."""
        executions.append(
            {
                "order_id": order_id,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return "incident created"

    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_incident",
                        "args": {
                            "order_id": "CMD-1042",
                            "reason": "Retard confirmé",
                            "idempotency_key": "hitl-test-CMD-1042",  # gitleaks:allow (test ID)
                        },
                        "id": "call-create-incident",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Traitement terminé."),
        ]
    )
    return create_agent(
        model=model,
        tools=[create_incident],
        middleware=[human_in_the_loop_middleware()],
        checkpointer=InMemorySaver(),
    )


async def start_sensitive_action(agent: Any, thread_id: str) -> Any:
    return await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Crée l'incident."}]},
        config={"configurable": {"thread_id": thread_id}},
        version="v2",
    )


async def sensitive_tool_is_not_executed_before_approval() -> None:
    executions: list[dict[str, str]] = []
    result = await start_sensitive_action(build_deterministic_agent(executions), str(uuid4()))
    assert result.interrupts
    assert executions == []


async def rejection_does_not_execute_sensitive_tool() -> None:
    executions: list[dict[str, str]] = []
    agent = build_deterministic_agent(executions)
    thread_id = str(uuid4())
    assert (await start_sensitive_action(agent, thread_id)).interrupts

    await agent.ainvoke(
        Command(
            resume={"decisions": [{"type": "reject", "message": "Action refusée pendant le test."}]}
        ),
        config={"configurable": {"thread_id": thread_id}},
        version="v2",
    )
    assert executions == []


async def approval_executes_sensitive_tool_exactly_once_with_same_key() -> None:
    executions: list[dict[str, str]] = []
    agent = build_deterministic_agent(executions)
    thread_id = str(uuid4())
    assert (await start_sensitive_action(agent, thread_id)).interrupts

    await agent.ainvoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config={"configurable": {"thread_id": thread_id}},
        version="v2",
    )
    assert executions == [
        {
            "order_id": "CMD-1042",
            "reason": "Retard confirmé",
            "idempotency_key": "hitl-test-CMD-1042",  # gitleaks:allow (test ID)
        }
    ]


def test_sensitive_tool_is_not_executed_before_approval() -> None:
    asyncio.run(sensitive_tool_is_not_executed_before_approval())


def test_rejection_does_not_execute_sensitive_tool() -> None:
    asyncio.run(rejection_does_not_execute_sensitive_tool())


def test_approval_executes_sensitive_tool_exactly_once_with_same_key() -> None:
    asyncio.run(approval_executes_sensitive_tool_exactly_once_with_same_key())
