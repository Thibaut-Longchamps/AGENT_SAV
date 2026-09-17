import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, cast
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from orderops.access import AppUser, Conversation, Role, can_decide, can_read_conversation
from orderops.agent.factory import build_agent
from orderops.config import get_settings
from orderops.db.session import dispose_engine
from orderops.rag.store import build_vector_store
from orderops.repositories.conversations import ConversationStore


class ChatRequest(BaseModel):
    thread_id: UUID
    message: str = Field(min_length=1, max_length=4000)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    message: str | None = Field(default=None, max_length=1000)


class NewConversationRequest(BaseModel):
    title: str = Field(default="Nouvelle conversation", min_length=1, max_length=120)


def graph_response(result: Any) -> dict[str, Any]:
    if result.interrupts:
        return {
            "status": "approval_required",
            "actions": jsonable_encoder([interrupt.value for interrupt in result.interrupts]),
        }

    messages = result.value.get("messages", [])
    content = messages[-1].content if messages else ""
    return {"status": "completed", "answer": jsonable_encoder(content)}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.demo_mode or settings.app_env == "production":
        raise RuntimeError("Ce MVP utilise des identités de démonstration sans authentification.")
    rag_engine, vector_store = build_vector_store(settings)
    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            writer, writer_client = await build_agent(settings, checkpointer, vector_store)
            reader, reader_client = await build_agent(
                settings, checkpointer, vector_store, role=Role.READER
            )
            app.state.agents = {Role.READER: reader, Role.OPERATOR: writer, Role.SUPERVISOR: writer}
            app.state.mcp_clients = [writer_client, reader_client]
            app.state.conversations = ConversationStore()
            app.state.thread_locks = {}
            yield
    finally:
        await rag_engine.dispose()
        await dispose_engine()


app = FastAPI(title="OrderOps AI Agent", version="0.1.0", lifespan=lifespan)


@app.exception_handler(httpx.HTTPStatusError)
async def upstream_status_error(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    if exc.response.status_code == 429:
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    "Le fournisseur IA limite actuellement les appels (429). "
                    "Patientez avant de réessayer et vérifiez les limites de votre compte Mistral."
                )
            },
        )
    return JSONResponse(
        status_code=502,
        content={"detail": "Un service externe a refusé la demande. Réessayez plus tard."},
    )


@app.exception_handler(httpx.RequestError)
async def upstream_request_error(request: Request, exc: httpx.RequestError) -> JSONResponse:
    timed_out = isinstance(exc, httpx.TimeoutException)
    return JSONResponse(
        status_code=504 if timed_out else 502,
        content={
            "detail": (
                "Un service externe met trop de temps à répondre. Réessayez plus tard."
                if timed_out
                else "Un service externe est inaccessible. Réessayez plus tard."
            )
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _thread_lock(request: Request, thread_id: str) -> asyncio.Lock:
    locks: dict[str, asyncio.Lock] = request.app.state.thread_locks
    return locks.setdefault(thread_id, asyncio.Lock())


async def current_user(
    request: Request,
    x_demo_user_id: Annotated[str | None, Header()] = None,
) -> AppUser:
    if not get_settings().demo_mode:
        raise HTTPException(403, "Mode de démonstration désactivé.")
    try:
        user_id = UUID(x_demo_user_id or "")
    except ValueError as exc:
        raise HTTPException(401, "Choisissez un profil de démonstration.") from exc
    store: ConversationStore = request.app.state.conversations
    user = await store.get_user(user_id)
    if user is None:
        raise HTTPException(401, "Profil inconnu ou désactivé.")
    return user


DemoUser = Annotated[AppUser, Depends(current_user)]


def _config(user: AppUser, thread_id: UUID, *, approved: bool = False) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": str(thread_id),
            "user_id": str(user.user_id),
            "approved": approved,
        }
    }


async def _conversation(request: Request, thread_id: UUID, user: AppUser) -> Conversation:
    store: ConversationStore = request.app.state.conversations
    conversation = await store.get(thread_id)
    if conversation is None or not can_read_conversation(user, conversation):
        raise HTTPException(404, "Conversation introuvable ou inaccessible.")
    return conversation


def _agent(request: Request, conversation: Conversation) -> Any:
    return request.app.state.agents[conversation.owner_role]


def _actions(snapshot: Any) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        jsonable_encoder([interrupt.value for interrupt in snapshot.interrupts]),
    )


async def _save_snapshot(
    request: Request,
    conversation: Conversation,
    user: AppUser,
    *,
    failed: bool = False,
    reviewer_id: UUID | None = None,
) -> Any:
    snapshot = await _agent(request, conversation).aget_state(_config(user, conversation.thread_id))
    await request.app.state.conversations.save_state(
        conversation.thread_id,
        actions=_actions(snapshot),
        failed=failed,
        reviewer_id=reviewer_id,
    )
    return snapshot


@app.get("/demo/users")
async def demo_users(request: Request) -> dict[str, Any]:
    if not get_settings().demo_mode:
        raise HTTPException(403, "Mode de démonstration désactivé.")
    return {
        "demo_mode": True,
        "users": jsonable_encoder(await request.app.state.conversations.list_users()),
    }


@app.post("/conversations", status_code=201)
async def new_conversation(
    payload: NewConversationRequest,
    request: Request,
    user: DemoUser,
) -> Any:
    return jsonable_encoder(
        await request.app.state.conversations.create(user, payload.title.strip())
    )


@app.get("/conversations")
async def conversations(request: Request, user: DemoUser) -> Any:
    return jsonable_encoder(await request.app.state.conversations.list_visible(user))


@app.get("/approvals")
async def approvals(request: Request, user: DemoUser) -> Any:
    if not user.can_approve:
        raise HTTPException(403, "Seul un superviseur peut accéder aux approbations.")
    return jsonable_encoder(
        await request.app.state.conversations.list_visible(user, pending_only=True)
    )


@app.get("/conversations/{thread_id}")
async def conversation_history(thread_id: UUID, request: Request, user: DemoUser) -> Any:
    conversation = await _conversation(request, thread_id, user)
    async with _thread_lock(request, str(thread_id)):
        snapshot = await _agent(request, conversation).aget_state(_config(user, thread_id))
    history = []
    for message in snapshot.values.get("messages", []):
        if isinstance(message, HumanMessage):
            history.append({"role": "user", "content": jsonable_encoder(message.content)})
        elif isinstance(message, AIMessage) and message.content:
            history.append({"role": "assistant", "content": jsonable_encoder(message.content)})
    return {
        **jsonable_encoder(conversation),
        "messages": history,
        "actions": _actions(snapshot),
        "can_chat": user.user_id == conversation.owner_id and not snapshot.interrupts,
        "can_decide": can_decide(user, conversation) and bool(snapshot.interrupts),
    }


@app.delete("/conversations/{thread_id}", status_code=204)
async def delete_conversation(thread_id: UUID, request: Request, user: DemoUser) -> None:
    async with _thread_lock(request, str(thread_id)):
        conversation = await _conversation(request, thread_id, user)
        if conversation.owner_id != user.user_id:
            raise HTTPException(403, "Seul le propriétaire peut supprimer ce chat.")
        # Les checkpoints sont supprimés avant les métadonnées ; un échec permet une reprise.
        # Cette suppression conserve les incidents, l'audit métier et les traces LangSmith.
        await _agent(request, conversation).checkpointer.adelete_thread(str(thread_id))
        await request.app.state.conversations.delete(thread_id)


@app.post("/chat")
async def chat(payload: ChatRequest, request: Request, user: DemoUser) -> dict[str, Any]:
    thread_id = str(payload.thread_id)
    async with _thread_lock(request, thread_id):
        conversation = await _conversation(request, payload.thread_id, user)
        if user.user_id != conversation.owner_id:
            raise HTTPException(403, "Seul le propriétaire peut envoyer des messages dans ce chat.")
        agent = _agent(request, conversation)
        config = _config(user, payload.thread_id)
        snapshot = await agent.aget_state(config)
        if snapshot.interrupts:
            raise HTTPException(409, "Une action attend la décision d'un superviseur.")
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": payload.message}]},
                config=config,
                version="v2",
            )
        except Exception:
            await _save_snapshot(request, conversation, user, failed=True)
            raise
        await _save_snapshot(request, conversation, user)

    response = graph_response(result)
    response["thread_id"] = thread_id
    return response


@app.post("/threads/{thread_id}/decision")
async def decide(
    thread_id: UUID,
    payload: DecisionRequest,
    request: Request,
    user: DemoUser,
) -> dict[str, Any]:
    key = str(thread_id)
    if not user.can_approve:
        raise HTTPException(403, "Seul un superviseur peut approuver ou refuser un incident.")
    decision: dict[str, str]
    if payload.decision == "approve":
        decision = {"type": "approve"}
    else:
        decision = {
            "type": "reject",
            "message": payload.message or "Action refusée. Ne pas réessayer.",
        }

    async with _thread_lock(request, key):
        conversation = await _conversation(request, thread_id, user)
        if not can_decide(user, conversation):
            raise HTTPException(403, "Conversation non autorisée pour une approbation.")
        snapshot = await _save_snapshot(request, conversation, user)
        action_count = sum(len(value.get("action_requests", [])) for value in _actions(snapshot))
        if not action_count:
            raise HTTPException(409, "Ce thread ne contient pas d'action pouvant être reprise.")
        try:
            result = await _agent(request, conversation).ainvoke(
                Command(resume={"decisions": [decision] * action_count}),
                config=_config(user, thread_id, approved=payload.decision == "approve"),
                version="v2",
            )
        except Exception:
            await _save_snapshot(request, conversation, user, failed=True, reviewer_id=user.user_id)
            raise
        await _save_snapshot(request, conversation, user, reviewer_id=user.user_id)

    response = graph_response(result)
    response["thread_id"] = key
    return response
