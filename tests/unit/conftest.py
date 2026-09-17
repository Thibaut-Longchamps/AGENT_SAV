from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from orderops.access import (
    DEMO_OPERATOR_ID,
    DEMO_READER_ID,
    DEMO_SUPERVISOR_ID,
    AppUser,
    Conversation,
    Role,
    can_read_conversation,
)
from orderops.api.main import app


class MemoryConversationStore:
    def __init__(self) -> None:
        self.users = {
            DEMO_READER_ID: AppUser(DEMO_READER_ID, "Lecteur", Role.READER),
            DEMO_OPERATOR_ID: AppUser(DEMO_OPERATOR_ID, "Opérateur", Role.OPERATOR),
            DEMO_SUPERVISOR_ID: AppUser(DEMO_SUPERVISOR_ID, "Superviseur", Role.SUPERVISOR),
        }
        self.chats = {}

    async def list_users(self):
        return [user for user in self.users.values() if user.active]

    async def get_user(self, key):
        user = self.users.get(key)
        return user if user and user.active else None

    async def create(self, user, title):
        chat = Conversation(uuid4(), user.user_id, user.name, user.role, title, "completed", [])
        self.chats[chat.thread_id] = chat
        return chat

    async def get(self, key):
        return self.chats.get(key)

    async def delete(self, key):
        self.chats.pop(key, None)

    async def list_visible(self, user, *, pending_only=False):
        return [
            chat
            for chat in self.chats.values()
            if can_read_conversation(user, chat)
            and (
                chat.status == "approval_required"
                if pending_only
                else chat.owner_id == user.user_id or chat.reviewer_id == user.user_id
            )
        ]

    async def save_state(self, key, *, actions, failed=False, reviewer_id=None):
        self.chats[key] = replace(
            self.chats[key],
            pending_actions=actions,
            status="approval_required" if actions else ("error" if failed else "completed"),
            reviewer_id=reviewer_id or self.chats[key].reviewer_id,
        )


class MemoryAgent:
    def __init__(self) -> None:
        self.checkpointer = self
        self.states = {}
        self.executions = 0
        self.calls = []

    async def adelete_thread(self, key):
        self.states.pop(key, None)

    async def aget_state(self, config):
        key = config["configurable"]["thread_id"]
        return self.states.get(key, SimpleNamespace(values={"messages": []}, interrupts=()))

    async def ainvoke(self, payload, *, config, **kwargs):
        self.calls.append(config)
        snapshot = await self.aget_state(config)
        messages = list(snapshot.values["messages"])
        interrupts = ()
        if isinstance(payload, Command):
            if payload.resume["decisions"][0]["type"] == "approve":
                self.executions += 1
            messages.append(AIMessage(content="Décision traitée."))
        else:
            text = payload["messages"][0]["content"]
            messages.append(HumanMessage(content=text))
            if "incident" in text:
                interrupts = (
                    SimpleNamespace(
                        value={
                            "action_requests": [
                                {"name": "create_incident", "args": {"order_id": "CMD-1042"}}
                            ]
                        }
                    ),
                )
            else:
                messages.append(AIMessage(content="Réponse sauvegardée."))
        new_state = SimpleNamespace(values={"messages": messages}, interrupts=interrupts)
        self.states[config["configurable"]["thread_id"]] = new_state
        return SimpleNamespace(value=new_state.values, interrupts=interrupts)


@pytest.fixture
def demo_api_state(monkeypatch):
    store = MemoryConversationStore()
    reader, writer = MemoryAgent(), MemoryAgent()
    agents = {Role.READER: reader, Role.OPERATOR: writer, Role.SUPERVISOR: writer}
    monkeypatch.setattr(app.state, "conversations", store, raising=False)
    monkeypatch.setattr(app.state, "agents", agents, raising=False)
    monkeypatch.setattr(app.state, "thread_locks", {}, raising=False)
    return SimpleNamespace(store=store, agents=agents)
