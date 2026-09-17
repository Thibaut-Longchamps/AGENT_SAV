import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from orderops.access import DEMO_OPERATOR_ID, DEMO_READER_ID, DEMO_SUPERVISOR_ID

UI_PATH = Path(__file__).resolve().parents[2] / "src/orderops/ui/app.py"


@pytest.fixture
def mock_ui_api(monkeypatch):
    profiles = [
        {"user_id": str(DEMO_READER_ID), "name": "Camille — Lecteur", "role": "reader"},
        {"user_id": str(DEMO_OPERATOR_ID), "name": "Alex — Opérateur SAV", "role": "operator"},
        {"user_id": str(DEMO_SUPERVISOR_ID), "name": "Sam — Superviseur", "role": "supervisor"},
    ]
    chats = {}
    original_client = httpx.Client
    state = {"rate_limited": False, "delete_failed": False, "chats": chats}

    def respond(request):
        path = request.url.path
        user = request.headers.get("X-Demo-User-Id")
        data = json.loads(request.content) if request.content else {}
        if path == "/demo/users":
            result = {"users": profiles}
        elif path == "/conversations" and request.method == "GET":
            result = [
                chat
                for chat in chats.values()
                if chat["owner_id"] == user or chat.get("reviewer_id") == user
            ]
        elif path == "/conversations":
            key = str(uuid4())
            chats[key] = {
                "thread_id": key,
                "owner_id": user,
                "owner_name": "Alex",
                "title": data["title"],
                "status": "completed",
                "actions": [],
                "messages": [],
            }
            result = chats[key]
        elif path == "/approvals":
            result = [chat for chat in chats.values() if chat["status"] == "approval_required"]
        elif path.startswith("/conversations/"):
            if request.method == "DELETE":
                if state["delete_failed"]:
                    return httpx.Response(503, json={"detail": "Suppression indisponible."})
                del chats[path.split("/")[-1]]
                return httpx.Response(204)
            chat = chats[path.split("/")[-1]]
            result = {
                **chat,
                "can_chat": chat["owner_id"] == user and not chat["actions"],
                "can_decide": user == str(DEMO_SUPERVISOR_ID) and bool(chat["actions"]),
            }
        elif path == "/chat":
            chat = chats[data["thread_id"]]
            chat["messages"].append({"role": "user", "content": data["message"]})
            if state["rate_limited"]:
                return httpx.Response(429, json={"detail": "Mistral limite les appels (429)."})
            chat["actions"] = [{"action_requests": [{"name": "create_incident"}]}]
            chat["status"] = "approval_required"
            result = {"status": "approval_required"}
        elif path.endswith("/decision"):
            chat = chats[path.split("/")[2]]
            chat["actions"] = []
            chat["status"] = "completed"
            chat["reviewer_id"] = user
            chat["messages"].append({"role": "assistant", "content": "Incident créé."})
            result = {"status": "completed"}
        else:
            raise AssertionError(f"Unexpected API request: {path}")
        return httpx.Response(200, json=result)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: original_client(
            *args, **kwargs, transport=httpx.MockTransport(respond)
        ),
    )
    return state


def test_operator_chat_can_be_reopened_and_reviewed_in_streamlit(mock_ui_api):
    ui = AppTest.from_file(UI_PATH).run(timeout=20)
    ui.sidebar.selectbox[0].set_value(str(DEMO_OPERATOR_ID)).run(timeout=20)
    ui.chat_input[0].set_value("Prépare un incident CMD-1042").run(timeout=20)
    assert not ui.exception
    key = next(iter(mock_ui_api["chats"]))
    assert ui.chat_input[0].disabled
    assert not any(button.label == "✅ Approuver" for button in ui.button)
    ui.sidebar.selectbox[0].set_value(str(DEMO_SUPERVISOR_ID)).run(timeout=20)
    ui.sidebar.selectbox[1].set_value(key).run(timeout=20)
    assert not ui.exception
    approve = next(button for button in ui.button if button.label == "✅ Approuver")
    approve.click().run(timeout=20)
    assert not ui.exception
    assert any(item.value == "Incident créé." for item in ui.markdown)
    reopened = AppTest.from_file(UI_PATH).run(timeout=20)
    reopened.sidebar.selectbox[0].set_value(str(DEMO_OPERATOR_ID)).run(timeout=20)
    reopened.sidebar.selectbox[1].set_value(key).run(timeout=20)
    assert not reopened.exception
    assert any(item.value == "Incident créé." for item in reopened.markdown)


def test_rate_limit_message_survives_streamlit_rerun(mock_ui_api):
    mock_ui_api["rate_limited"] = True
    ui = AppTest.from_file(UI_PATH).run(timeout=20)
    ui.chat_input[0].set_value("CMD-1042").run(timeout=20)
    assert not ui.exception
    assert ui.error[0].value == "Mistral limite les appels (429)."
    ui.run(timeout=20)
    assert ui.error[0].value == "Mistral limite les appels (429)."


def test_delete_chat_requires_confirmation_and_can_be_cancelled(mock_ui_api):
    ui = AppTest.from_file(UI_PATH).run(timeout=20)
    ui.chat_input[0].set_value("CMD-1042").run(timeout=20)
    key = next(iter(mock_ui_api["chats"]))

    def click(label):
        next(button for button in ui.button if button.label == label).click().run(timeout=20)
        assert not ui.exception

    click("🗑️ Supprimer ce chat")
    assert key in mock_ui_api["chats"]
    assert any("propositions en attente" in warning.value for warning in ui.warning)
    click("Annuler")
    assert key in mock_ui_api["chats"]
    assert not any(button.label == "Confirmer la suppression" for button in ui.button)
    click("🗑️ Supprimer ce chat")
    click("Confirmer la suppression")
    assert key not in mock_ui_api["chats"]
    assert ui.sidebar.selectbox[1].value == ""
    assert not ui.chat_input[0].disabled
    assert any("Chat supprimé" in message.value for message in ui.success)
    reopened = AppTest.from_file(UI_PATH).run(timeout=20)
    assert reopened.sidebar.selectbox[1].options == ["Nouvelle conversation"]


def test_supervisor_has_no_delete_button_for_operator_chat(mock_ui_api):
    ui = AppTest.from_file(UI_PATH).run(timeout=20)
    ui.sidebar.selectbox[0].set_value(str(DEMO_OPERATOR_ID)).run(timeout=20)
    ui.chat_input[0].set_value("Prépare un incident").run(timeout=20)
    key = next(iter(mock_ui_api["chats"]))
    ui.sidebar.selectbox[0].set_value(str(DEMO_SUPERVISOR_ID)).run(timeout=20)
    ui.sidebar.selectbox[1].set_value(key).run(timeout=20)
    assert not ui.exception
    assert not any(button.label == "🗑️ Supprimer ce chat" for button in ui.button)


def test_failed_deletion_keeps_chat_and_allows_retry(mock_ui_api):
    ui = AppTest.from_file(UI_PATH).run(timeout=20)
    ui.chat_input[0].set_value("CMD-1042").run(timeout=20)
    key = next(iter(mock_ui_api["chats"]))
    mock_ui_api["delete_failed"] = True
    next(button for button in ui.button if button.label == "🗑️ Supprimer ce chat").click().run(
        timeout=20
    )
    next(button for button in ui.button if button.label == "Confirmer la suppression").click().run(
        timeout=20
    )
    assert not ui.exception
    assert key in mock_ui_api["chats"]
    assert ui.sidebar.selectbox[1].value == key
    assert ui.error[0].value == "Suppression indisponible."
    assert not ui.success
    mock_ui_api["delete_failed"] = False
    next(button for button in ui.button if button.label == "Confirmer la suppression").click().run(
        timeout=20
    )
    assert not ui.exception
    assert key not in mock_ui_api["chats"]
