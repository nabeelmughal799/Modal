import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google.genai.errors import APIError as GoogleAPIError
from httpx2 import HTTPError as HttpClientError

from dashboard import show_dashboard
from assistant import (
    FILE_ONLY_QUESTION,
    ask_agent,
    make_weather_pdf,
    transcribe_audio,
)
from attachments import (
    MAX_ATTACHMENTS,
    MAX_FILE_BYTES,
    validate_attachments,
)
from chat_store import chat_title
from guest_store import (
    add_guest_message,
    create_guest_chat,
    list_guest_chats,
    load_guest_active_attachments,
    save_guest_attachment,
    set_guest_chat_title,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def get_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except FileNotFoundError:
        return None


def reset_composer() -> None:
    st.session_state.pop("voice_files", None)
    st.session_state.pop("voice_draft", None)
    st.session_state["composer_nonce"] = st.session_state.get("composer_nonce", 0) + 1


def render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        if message["content"]:
            st.markdown(message["content"])
        for attachment in message.get("attachments", []):
            st.caption(f"Attached: {attachment['file_name']}")

        metadata = message.get("metadata") or {}
        for graph in metadata.get("diagrams", []):
            st.graphviz_chart(graph)

        if metadata.get("weather"):
            try:
                if "pdf_data" not in message:
                    message["pdf_data"] = make_weather_pdf(
                        {"content": message["content"], "metadata": metadata}
                    )
            except ValueError as error:
                st.warning(str(error))
            else:
                st.download_button(
                    "Download weather PDF",
                    data=message["pdf_data"],
                    file_name=f"weather-{message['id']}.pdf",
                    mime="application/pdf",
                    key=f"weather-pdf-{message['id']}",
                )


def show_chat_sidebar() -> tuple[dict | None, list[dict]]:
    chats = list_guest_chats(st.session_state.setdefault("guest_chats", {}))
    chat_ids = {chat["id"] for chat in chats}

    with st.sidebar:
        st.title("Chats")
        if st.button("New chat", use_container_width=True):
            st.session_state["active_chat_id"] = None
            st.session_state["new_chat_requested"] = True
            reset_composer()
            st.rerun()

        selected_id = st.session_state.get("active_chat_id")
        if selected_id not in chat_ids:
            selected_id = None
            if not st.session_state.get("new_chat_requested") and chats:
                selected_id = chats[0]["id"]
                st.session_state["active_chat_id"] = selected_id

        for chat in chats:
            if st.button(
                chat["title"],
                key=f"open-chat-{chat['id']}",
                use_container_width=True,
                type="primary" if chat["id"] == selected_id else "secondary",
            ):
                st.session_state["active_chat_id"] = chat["id"]
                st.session_state["new_chat_requested"] = False
                reset_composer()
                st.rerun()

        st.divider()
        st.caption("Guest mode · chats last for this session")

    active_chat = next((chat for chat in chats if chat["id"] == selected_id), None)
    messages = active_chat["messages"] if active_chat else []
    return active_chat, messages


def save_and_answer(
    chat: dict | None,
    messages: list[dict],
    question: str,
    files: list[tuple[str, bytes]],
) -> None:
    prepared = validate_attachments(files)
    if not question.strip() and not prepared:
        raise ValueError("Type a question, attach a file, or record a voice question.")
    google_api_key = get_secret("GOOGLE_API_KEY")
    if question.strip() and not google_api_key:
        raise ValueError("Set GOOGLE_API_KEY in Streamlit Secrets.")

    file_names = [attachment.file_name for attachment in prepared]
    first_user_message = not any(row["role"] == "user" for row in messages)
    title = chat_title(question, file_names)
    chats = st.session_state.setdefault("guest_chats", {})
    if chat is None:
        chat = create_guest_chat(chats, title)
        st.session_state["active_chat_id"] = chat["id"]
        st.session_state["new_chat_requested"] = False
    elif first_user_message:
        set_guest_chat_title(chat, title)

    messages = list(messages)  # Snapshot before appending this turn.
    user_message = add_guest_message(
        chat,
        "user",
        question.strip(),
    )
    stored_attachments = [
        save_guest_attachment(chat, user_message["id"], attachment)
        for attachment in prepared
    ]

    render_message(user_message)
    active_ids = (
        [attachment["id"] for attachment in stored_attachments]
        if stored_attachments
        else chat.get("active_attachment_ids", [])
    )
    if stored_attachments:
        chat["active_attachment_ids"] = active_ids

    if not question.strip() and stored_attachments:
        add_guest_message(
            chat,
            "assistant",
            FILE_ONLY_QUESTION,
        )
        return
    if not question.strip():
        raise ValueError("Type a question, attach a file, or record a voice question.")

    active_attachments = load_guest_active_attachments(chat, active_ids)
    previous_history = [
        {"role": row["role"], "content": row["content"]}
        for row in messages
        if row.get("content")
    ]
    reply = ask_agent(
        previous_history,
        question,
        active_attachments,
        google_api_key,
        get_secret("WEATHER_API_KEY") or "",
        get_secret("TAVILY_API_KEY") or "",
    )
    add_guest_message(
        chat,
        "assistant",
        reply["content"],
        reply["metadata"],
    )


st.set_page_config(page_title="Nabeel", page_icon="🌤️", layout="wide")
st.title("Nabeel")
# Pass Google API key to dashboard for city briefing generation
st.session_state["_google_api_key_for_briefing"] = get_secret("GOOGLE_API_KEY")
show_dashboard(get_secret("WEATHER_API_KEY"))
st.divider()
st.subheader("Ask the assistant")

active_chat, messages = show_chat_sidebar()
for message in messages:
    render_message(message)

nonce = st.session_state.get("composer_nonce", 0)
key = f"composer-{nonce}"
report = st.session_state.get("dashboard_weather", {})
city = report.get("city", "Lahore, Pakistan")
for column, (label, question) in zip(st.columns(3), [
    ("Rain timing", f"When could it rain in {city} over the next 12 hours?"),
    ("Storm outlook", f"Explain the thunderstorm outlook for {city} over the next 12 hours."),
    ("News briefing", f"Write a short weather bulletin for {city} with current conditions and the next 12 hours."),
]):
    if column.button(label, width="stretch"):
        st.session_state["voice_draft"] = question
pending_files = st.session_state.get("voice_files", [])
if pending_files:
    st.caption("Attached to draft: " + ", ".join(name for name, _ in pending_files))
    if st.button("Remove draft attachments"):
        st.session_state.pop("voice_files", None)
        st.rerun()

# Voice becomes an editable draft. Enter submits the reviewed text.
if "voice_draft" in st.session_state:
    st.session_state[key] = st.session_state.pop("voice_draft")
prompt = st.chat_input(
    "Ask a question…",
    key=key,
    accept_file="multiple",
    file_type=["pdf", "docx", "txt", "jpg", "jpeg", "png"],
    accept_audio=True,
    max_upload_size=MAX_FILE_BYTES // (1024 * 1024),
)
if prompt:
    files = pending_files + [(item.name, item.getvalue()) for item in prompt.files]
    try:
        if prompt.audio is not None:
            google_key = get_secret("GOOGLE_API_KEY")
            if not google_key:
                raise ValueError("Set GOOGLE_API_KEY to transcribe a recording.")
            if len(files) > MAX_ATTACHMENTS:
                raise ValueError(f"Attach up to {MAX_ATTACHMENTS} files.")
            with st.spinner("Transcribing your recording…"):
                transcript = transcribe_audio(prompt.audio.getvalue(), google_key)
            st.session_state["voice_draft"] = " ".join(filter(None, [prompt.text, transcript]))
            st.session_state["voice_files"] = files
            st.rerun()
        with st.spinner("Preparing your answer…"):
            save_and_answer(active_chat, messages, prompt.text, files)
    except ValueError as error:
        st.warning(str(error))
    except Exception as error:
        detail = str(error).upper()
        if "503" in detail or "UNAVAILABLE" in detail:
            st.warning("Gemini is busy. Try sending again shortly.")
        elif "429" in detail or "RESOURCE_EXHAUSTED" in detail:
            st.warning("Gemini request limit reached. Please try again later.")
        else:
            st.error("The assistant could not finish. Check the connection and Gemini configuration.")
    else:
        reset_composer()
        st.rerun()
