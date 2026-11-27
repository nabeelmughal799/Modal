import hashlib
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google.genai.errors import APIError as GoogleAPIError
from httpx2 import HTTPError as HttpClientError

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
                pdf_data = make_weather_pdf(
                    {"content": message["content"], "metadata": metadata}
                )
            except ValueError as error:
                st.warning(str(error))
            else:
                st.download_button(
                    "Download weather PDF",
                    data=pdf_data,
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


def render_composer(google_api_key: str | None) -> tuple[str, list[tuple[str, bytes]], bool]:
    nonce = st.session_state.get("composer_nonce", 0)
    question_key = f"question-{nonce}"
    audio_key = f"audio-{nonce}"
    audio_hash_key = f"audio-hash-{nonce}"
    upload_key = f"uploads-{nonce}"

    question_column, microphone_column = st.columns([8, 2])
    with microphone_column:
        audio = st.audio_input(
            "Record a question",
            sample_rate=16000,
            key=audio_key,
        )

    if audio is not None:
        audio_bytes = audio.getvalue()
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
        if st.session_state.get(audio_hash_key) != audio_hash:
            st.session_state[audio_hash_key] = audio_hash
            if not google_api_key:
                st.warning("Add GOOGLE_API_KEY to transcribe a recording.")
            else:
                try:
                    st.session_state[question_key] = transcribe_audio(
                        audio_bytes, google_api_key
                    )
                except (GoogleAPIError, HttpClientError, ValueError) as error:
                    st.warning(f"Transcription failed: {error}")
                else:
                    st.caption("Review or edit the transcript before sending.")

    with question_column:
        st.text_input(
            "Message",
            key=question_key,
            placeholder="Type a question or review the transcript...",
            label_visibility="collapsed",
        )

    uploads = st.file_uploader(
        "Attach PDF, DOCX, TXT, JPG, or PNG files",
        type=["pdf", "docx", "txt", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key=upload_key,
        help=(
            f"Up to {MAX_ATTACHMENTS} files per message; "
            f"{MAX_FILE_BYTES // (1024 * 1024)} MB per file."
        ),
    )
    send = st.button("Send", type="primary", use_container_width=True)
    files = [(item.name, item.getvalue()) for item in uploads] if uploads else []
    return st.session_state.get(question_key, ""), files, send


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

    user_message = add_guest_message(
        chat,
        "user",
        question.strip(),
    )
    stored_attachments = [
        save_guest_attachment(chat, user_message["id"], attachment)
        for attachment in prepared
    ]

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


st.set_page_config(page_title="My AI Assistant", layout="wide")
st.title("My AI Assistant")

active_chat, messages = show_chat_sidebar()
for message in messages:
    render_message(message)

question, uploaded_files, send = render_composer(get_secret("GOOGLE_API_KEY"))
if send:
    try:
        save_and_answer(
            active_chat,
            messages,
            question,
            uploaded_files,
        )
    except (
        ValueError,
        GoogleAPIError,
        HttpClientError,
    ) as error:
        st.session_state["flash_error"] = str(error)
    else:
        st.session_state.pop("flash_error", None)
    reset_composer()
    st.rerun()

flash_error = st.session_state.pop("flash_error", None)
if flash_error:
    st.error(f"Could not send the message: {flash_error}")
