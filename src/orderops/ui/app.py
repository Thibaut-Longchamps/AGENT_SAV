# Interface Streamlit : profils, conversations et messages.
# Les actions sont transmises à FastAPI ; SQL, RAG et appels LLM restent côté serveur.

import os
from typing import cast

import httpx
import streamlit as st

from orderops.ui.errors import api_error_message

API_URL = os.getenv("ORDEROPS_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="OrderOps AI Agent", page_icon="📦", layout="centered")
st.title("📦 OrderOps AI Agent")
st.markdown(
    "Votre assistant pour l'administration des ventes et le service après-vente. "
    "Posez vos questions en langage naturel pour consulter une commande ou un client, "
    "suivre une livraison, vérifier les stocks et retrouver les procédures applicables. "
    "OrderOps peut aussi préparer un incident SAV : **un superviseur doit l'approuver "
    "avant sa création**."
)
st.caption(
    "Pour commencer : « Donne-moi les informations de CMD-1042 » "
    "ou « Combien de SKU-12 sont disponibles ? »"
)

if "api_error" not in st.session_state:
    st.session_state.api_error = None


def call_api(method: str, path: str, payload: dict[str, object] | None = None) -> object:
    user_id = st.session_state.get("active_user_id")
    headers = {"X-Demo-User-Id": user_id} if user_id else {}
    with httpx.Client(timeout=90) as client:
        response = client.request(method, f"{API_URL}{path}", json=payload, headers=headers)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()


st.warning("Mode démonstration : profils simulés, sans authentification. Usage local uniquement.")
try:
    profiles = cast(dict, call_api("GET", "/demo/users"))["users"]
except httpx.HTTPError as exc:
    st.error(api_error_message(exc))
    st.stop()
if not profiles:
    st.error("Aucun profil disponible. Appliquez les migrations Alembic.")
    st.stop()

profile_by_id = {profile["user_id"]: profile for profile in profiles}
selected_user = st.sidebar.selectbox(
    "Profil de démonstration",
    list(profile_by_id),
    format_func=lambda key: profile_by_id[key]["name"],
    key="demo_user",
)
if st.session_state.get("active_user_id") != selected_user:
    st.session_state.active_user_id = selected_user
    st.session_state.chat_choice = ""
    st.session_state.api_error = None
    st.session_state.pop("next_thread", None)
    st.session_state.pop("delete_target", None)
profile = profile_by_id[selected_user]
role = profile["role"]
descriptions = {
    "reader": "Lecteur : commandes, clients, livraisons, stocks et procédures. Aucune écriture.",
    "operator": (
        "Opérateur SAV : consultation et proposition d'incidents. Validation par superviseur."
    ),
    "supervisor": "Superviseur : consultation, proposition et approbation/refus des incidents.",
}
st.sidebar.info(descriptions[role])
st.sidebar.caption("Les chats sont sauvegardés dans PostgreSQL et liés au profil choisi.")
if st.sidebar.button("＋ Nouvelle conversation", use_container_width=True):
    st.session_state.chat_choice = ""
    st.session_state.api_error = None
    st.session_state.pop("delete_target", None)
st.sidebar.button("↻ Actualiser les conversations", use_container_width=True)

try:
    saved = cast(list[dict], call_api("GET", "/conversations"))
    approvals = cast(list[dict], call_api("GET", "/approvals")) if role == "supervisor" else []
except httpx.HTTPError as exc:
    st.error(api_error_message(exc))
    st.stop()
all_chats = {chat["thread_id"]: chat for chat in saved + approvals}
options = [""] + list(all_chats)
if "next_thread" in st.session_state:
    st.session_state.chat_choice = st.session_state.pop("next_thread")
if st.session_state.get("chat_choice", "") not in options:
    st.session_state.chat_choice = ""


def chat_label(key: str) -> str:
    if not key:
        return "Nouvelle conversation"
    chat = all_chats[key]
    prefix = "⏳ " if chat["status"] == "approval_required" else ""
    owner = f" — {chat['owner_name']}" if chat["owner_id"] != selected_user else ""
    return f"{prefix}{chat['title']}{owner}"


thread_id = st.sidebar.selectbox(
    "Mes chats et demandes accessibles",
    options,
    format_func=chat_label,
    key="chat_choice",
)
if st.session_state.get("delete_target") != thread_id:
    st.session_state.pop("delete_target", None)
if role == "supervisor":
    st.sidebar.caption(f"{len(approvals)} conversation(s) en attente d'approbation")

current: dict = {"messages": [], "actions": [], "can_chat": True, "can_decide": False}
if thread_id:
    try:
        current = cast(dict, call_api("GET", f"/conversations/{thread_id}"))
    except httpx.HTTPError as exc:
        st.error(api_error_message(exc))
        st.stop()
    st.caption(f"Conversation : {current['title']}")
    if current.get("status") == "error":
        st.warning(
            "Le dernier traitement a rencontré une erreur. L'historique est conservé ; "
            "si une action avait été approuvée, vérifiez son résultat avant de la reproposer."
        )
    if current["owner_id"] == selected_user:
        with st.sidebar:
            if st.button("🗑️ Supprimer ce chat", use_container_width=True):
                st.session_state.delete_target = thread_id
            if st.session_state.get("delete_target") == thread_id:
                st.warning(f"Supprimer définitivement « {current['title']} » ?")
                st.caption(
                    "L'historique sera effacé, sans possibilité d'annulation. "
                    "Les incidents déjà créés et leur audit restent conservés."
                )
                if current["actions"]:
                    st.warning("Les propositions en attente seront annulées, sans être exécutées.")
                confirm_column, cancel_column = st.columns(2)
                confirm = confirm_column.button("Confirmer la suppression", type="primary")
                cancel = cancel_column.button("Annuler")
                if cancel:
                    st.session_state.pop("delete_target", None)
                    st.rerun()
                if confirm:
                    try:
                        with st.spinner("Suppression du chat…"):
                            call_api("DELETE", f"/conversations/{thread_id}")
                    except httpx.HTTPError as exc:
                        st.session_state.api_error = api_error_message(exc)
                    else:
                        st.session_state.pop("delete_target", None)
                        st.session_state.next_thread = ""
                        st.session_state.api_error = None
                        st.session_state.chat_deleted = True
                    st.rerun()
if st.session_state.pop("chat_deleted", False):
    st.success("Chat supprimé. Vous pouvez commencer une nouvelle conversation.")
for message in current["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if st.session_state.api_error:
    st.error(st.session_state.api_error)

user_message = st.chat_input(
    "Exemple : ACME n'a pas reçu CMD-1042",
    disabled=not current["can_chat"],
    max_chars=4000,
)
if user_message:
    st.session_state.api_error = None
    try:
        with st.spinner("Vérification des données et préparation de la réponse…"):
            if not thread_id:
                new_chat = cast(
                    dict, call_api("POST", "/conversations", {"title": user_message[:120]})
                )
                thread_id = new_chat["thread_id"]
                st.session_state.next_thread = thread_id
            call_api("POST", "/chat", {"thread_id": thread_id, "message": user_message})
    except httpx.HTTPError as exc:
        st.session_state.api_error = api_error_message(exc)
    st.rerun()

if current["actions"]:
    st.warning("Une action sensible attend la validation d'un superviseur.")
    st.json(current["actions"])
    if not current["can_decide"]:
        st.info("Passez au profil Superviseur et sélectionnez cette conversation pour la traiter.")
    else:
        st.caption("Approuver exécute réellement toutes les actions affichées dans la base locale.")
        approve_column, reject_column = st.columns(2)
        approve = approve_column.button("✅ Approuver", use_container_width=True)
        reject = reject_column.button("❌ Refuser", use_container_width=True)
        if approve or reject:
            st.session_state.api_error = None
            try:
                with st.spinner("Traitement de la décision…"):
                    call_api(
                        "POST",
                        f"/threads/{thread_id}/decision",
                        {"decision": "approve" if approve else "reject"},
                    )
            except httpx.HTTPError as exc:
                st.session_state.api_error = api_error_message(exc)
            st.rerun()
elif thread_id and not current["can_chat"]:
    st.info("Cette conversation appartient à un autre profil : consultation uniquement.")
