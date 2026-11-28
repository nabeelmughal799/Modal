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
from attachments import MAX_ATTACHMENTS, MAX_FILE_BYTES, validate_attachments
from chat_store import chat_title
from guest_store import (
    add_guest_message,
    create_guest_chat,
    list_guest_chats,
    load_guest_active_attachments,
    save_guest_attachment,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def get_secret(name):
    """Local .env ya Streamlit Cloud Secrets se key lo."""
    value = os.getenv(name)
    if value:
        return value

    try:
        return st.secrets.get(name)
    except FileNotFoundError:
        return None


def reset_composer():
    """Chat change ya send hone par purani voice aur files clear karo."""
    st.session_state.pop("voice_files", None)
    st.session_state.pop("voice_draft", None)
    st.session_state["composer_nonce"] = st.session_state.get("composer_nonce", 0) + 1


def render_message(message):
    with st.chat_message(message["role"]):
        if message["content"]:
            st.markdown(message["content"])

        for file in message.get("attachments", []):
            st.caption(f"Attached: {file['file_name']}")

        metadata = message.get("metadata") or {}

        for diagram in metadata.get("diagrams", []):
            st.graphviz_chart(diagram)

        if metadata.get("weather"):
            try:
                # PDF ek baar banti hai, phir isi chat se dobara download hoti hai.
                if "pdf_data" not in message:
                    message["pdf_data"] = make_weather_pdf({
                        "content": message["content"],
                        "metadata": metadata,
                    })

                st.download_button(
                    "Download weather PDF",
                    data=message["pdf_data"],
                    file_name=f"weather-{message['id']}.pdf",
                    mime="application/pdf",
                    key=f"pdf-{message['id']}",
                )
            except ValueError as error:
                st.warning(str(error))


def show_sidebar():
    chats = st.session_state.setdefault("guest_chats", {})

    with st.sidebar:
        st.title("Chats")

        if st.button("New chat", width="stretch"):
            st.session_state["active_chat_id"] = None
            reset_composer()
            st.rerun()

        for chat in list_guest_chats(chats):
            selected = chat["id"] == st.session_state.get("active_chat_id")

            if st.button(
                chat["title"],
                key=f"open-{chat['id']}",
                type="primary" if selected else "secondary",
                width="stretch",
            ):
                st.session_state["active_chat_id"] = chat["id"]
                reset_composer()
                st.rerun()

        st.divider()
        st.caption("Guest mode · chats last for this session")

    return chats.get(st.session_state.get("active_chat_id"))


def send_message(chat, question, files):
    question = question.strip()
    attachments = validate_attachments(files)

    if not question and not attachments:
        raise ValueError("Type a question or attach a file.")

    google_key = get_secret("GOOGLE_API_KEY")
    if question and not google_key:
        raise ValueError("Set GOOGLE_API_KEY in Streamlit Secrets.")

    if chat is None:
        file_names = [file.file_name for file in attachments]
        title = chat_title(question, file_names)
        chat = create_guest_chat(st.session_state["guest_chats"], title)
        st.session_state["active_chat_id"] = chat["id"]

    # Naya sawal add karne se pehle history lo, taake sawal do baar na jaye.
    history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in chat["messages"]
        if msg.get("content")
    ]

    user_message = add_guest_message(chat, "user", question)

    if attachments:
        saved = [
            save_guest_attachment(chat, user_message["id"], file)
            for file in attachments
        ]
        chat["active_attachment_ids"] = [file["id"] for file in saved]

    # Agent ke jawab ka intezar karte hue user ko apna message nazar aata hai.
    render_message(user_message)

    if not question:
        add_guest_message(chat, "assistant", FILE_ONLY_QUESTION)
        return

    active_files = load_guest_active_attachments(
        chat, chat.get("active_attachment_ids", [])
    )

    reply = ask_agent(
        history,
        question,
        active_files,
        google_key,
        get_secret("WEATHER_API_KEY") or "",
        get_secret("TAVILY_API_KEY") or "",
    )

    add_guest_message(chat, "assistant", reply["content"], reply["metadata"])


# -------------------- Streamlit UI --------------------

st.set_page_config(
    page_title="Weather Assistant",
    page_icon="🌤️",
    layout="centered",
)

st.title("Weather Assistant")
active_chat = show_sidebar()

if active_chat:
    for message in active_chat["messages"]:
        render_message(message)

nonce = st.session_state.get("composer_nonce", 0)
input_key = f"composer-{nonce}"
pending_files = st.session_state.get("voice_files", [])

if pending_files:
    names = ", ".join(name for name, _ in pending_files)
    st.caption(f"Attached to draft: {names}")

    if st.button("Remove draft attachments"):
        st.session_state.pop("voice_files", None)
        st.rerun()

# Voice transcript isi input mein aata hai, jahan user usay edit kar sakta hai.
if "voice_draft" in st.session_state:
    st.session_state[input_key] = st.session_state.pop("voice_draft")

# Ek field: left par upload, right par mic. Enter se message send hota hai.
prompt = st.chat_input(
    "Apna sawal yahan likhein…",
    key=input_key,
    accept_file="multiple",
    file_type=["pdf", "docx", "txt", "jpg", "jpeg", "png"],
    accept_audio=True,
    max_upload_size=MAX_FILE_BYTES // (1024 * 1024),
)

if prompt:
    files = pending_files + [
        (file.name, file.getvalue()) for file in prompt.files
    ]

    try:
        if prompt.audio is not None:
            google_key = get_secret("GOOGLE_API_KEY")

            if not google_key:
                raise ValueError("Voice ke liye GOOGLE_API_KEY add karein.")

            if len(files) > MAX_ATTACHMENTS:
                raise ValueError(f"Maximum {MAX_ATTACHMENTS} files attach karein.")

            with st.spinner("Voice ko text mein badal raha hoon…"):
                transcript = transcribe_audio(prompt.audio.getvalue(), google_key)

            st.session_state["voice_draft"] = " ".join(
                filter(None, [prompt.text, transcript])
            )
            st.session_state["voice_files"] = files
            st.rerun()

        with st.spinner("Jawab tayyar ho raha hai…"):
            send_message(active_chat, prompt.text, files)

    except (ValueError, GoogleAPIError, HttpClientError) as error:
        st.error(f"Message send nahi hua. {error}")

    else:
        reset_composer()
        st.rerun()