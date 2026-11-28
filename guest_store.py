"""Session-only chat and attachment storage for guest mode."""

from time import time
from uuid import uuid4

from attachments import PreparedAttachment


def list_guest_chats(chats: dict[str, dict]) -> list[dict]:
    return sorted(chats.values(), key=lambda chat: chat["updated_at"], reverse=True)


def create_guest_chat(chats: dict[str, dict], title: str) -> dict:
    now = time()
    chat = {
        "id": str(uuid4()),
        "title": title,
        "updated_at": now,
        "active_attachment_ids": [],
        "messages": [],
        "attachments": {},
    }
    chats[chat["id"]] = chat
    return chat


def set_guest_chat_title(chat: dict, title: str) -> None:
    chat["title"] = title
    chat["updated_at"] = time()


def add_guest_message(
    chat: dict, role: str, content: str, metadata: dict | None = None
) -> dict:
    message = {
        "id": str(uuid4()),
        "role": role,
        "content": content,
        "metadata": metadata or {},
        "attachments": [],
    }
    chat["messages"].append(message)
    chat["updated_at"] = time()
    return message


def save_guest_attachment(
    chat: dict, message_id: str, attachment: PreparedAttachment
) -> dict:
    record = {
        "id": str(uuid4()),
        "message_id": message_id,
        "file_name": attachment.file_name,
        "mime_type": attachment.mime_type,
        "extracted_text": attachment.extracted_text,
        "data": attachment.data,
    }
    chat["attachments"][record["id"]] = record
    for message in chat["messages"]:
        if message["id"] == message_id:
            message["attachments"].append(
                {"id": record["id"], "file_name": record["file_name"]}
            )
            break
    return record


def load_guest_active_attachments(chat: dict, attachment_ids: list[str]) -> list[dict]:
    attachments = []
    for attachment_id in attachment_ids:
        record = chat["attachments"].get(attachment_id)
        if record is None:
            continue
        attachment = {**record, "image_bytes": b""}
        if record["mime_type"].startswith("image/"):
            attachment["image_bytes"] = record["data"]
        attachments.append(attachment)
    return attachments
