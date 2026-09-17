from types import SimpleNamespace

import httpx
import pytest

from orderops.access import DEMO_SUPERVISOR_ID, Role
from orderops.api.main import app
from orderops.ui.errors import api_error_message


class FailingAgent:
    def __init__(self, error: httpx.HTTPError, *, pending: bool = False) -> None:
        self.error = error
        self.pending = pending

    async def aget_state(self, *args: object, **kwargs: object) -> SimpleNamespace:
        interrupts = (
            (
                SimpleNamespace(
                    value={
                        "action_requests": [
                            {"name": "create_incident", "args": {"order_id": "CMD-1042"}}
                        ]
                    }
                ),
            )
            if self.pending
            else ()
        )
        return SimpleNamespace(values={"messages": []}, interrupts=interrupts)

    async def ainvoke(self, *args: object, **kwargs: object) -> None:
        raise self.error


@pytest.mark.parametrize("route", ["chat", "decision"])
@pytest.mark.parametrize("status", [429, 401, 503])
async def test_upstream_error_is_readable_on_both_routes(
    route: str, status: int, monkeypatch: pytest.MonkeyPatch, demo_api_state
) -> None:
    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    error = httpx.HTTPStatusError(
        "private upstream message",
        request=request,
        response=httpx.Response(status, request=request),
    )
    demo_api_state.agents[Role.SUPERVISOR] = FailingAgent(error, pending=route == "decision")
    chat = await demo_api_state.store.create(demo_api_state.store.users[DEMO_SUPERVISOR_ID], "test")
    thread_id = str(chat.thread_id)
    path = "/chat" if route == "chat" else f"/threads/{thread_id}/decision"
    payload = (
        {"thread_id": thread_id, "message": "CMD-1042"}
        if route == "chat"
        else {"decision": "approve"}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Demo-User-Id": str(DEMO_SUPERVISOR_ID)},
    ) as client:
        response = await client.post(path, json=payload)
    assert response.status_code == (429 if status == 429 else 502)
    assert "private upstream message" not in response.text
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    assert api_error_message(caught.value) == response.json()["detail"]


@pytest.mark.parametrize("route", ["chat", "decision"])
async def test_upstream_timeout_is_not_reported_as_invalid_thread(
    route: str, monkeypatch: pytest.MonkeyPatch, demo_api_state
) -> None:
    demo_api_state.agents[Role.SUPERVISOR] = FailingAgent(
        httpx.ReadTimeout("timeout"), pending=route == "decision"
    )
    chat = await demo_api_state.store.create(demo_api_state.store.users[DEMO_SUPERVISOR_ID], "test")
    thread_id = str(chat.thread_id)
    path = "/chat" if route == "chat" else f"/threads/{thread_id}/decision"
    payload = (
        {"thread_id": thread_id, "message": "CMD-1042"}
        if route == "chat"
        else {"decision": "approve"}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Demo-User-Id": str(DEMO_SUPERVISOR_ID)},
    ) as client:
        response = await client.post(path, json=payload)
    assert response.status_code == 504
    assert "temps" in response.json()["detail"]
