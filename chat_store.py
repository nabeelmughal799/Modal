"""Supabase Auth, database, and private storage helpers for chat history."""

from uuid import uuid4

from supabase import Client, create_client

from attachments import PreparedAttachment

ATTACHMENT_BUCKET = "chat-attachments"


def new_client(url: str, anon_key: str) -> Client:
    return create_client(url, anon_key)


def chat_title(question: str, file_names: list[str]) -> str:
    source = question.strip() or (f"File: {file_names[0]}" if file_names else "New chat")
    title = " ".join(source.split())
    return title[:60] + ("..." if len(title) > 60 else "")


def list_chats(client: Client, user_id: str) -> list[dict]:
    result = (
        client.table("chats")
        .select("id,title,updated_at,active_attachment_ids")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


def create_chat(client: Client, user_id: str, title: str) -> dict:
    result = (
        client.table("chats")
        .insert({"user_id": user_id, "title": title})
        .execute()
    )
    return result.data[0]


def update_chat(
    client: Client,
    user_id: str,
    chat_id: str,
    title: str,
    attachment_ids: list[str],
) -> None:
    (
        client.table("chats")
        .update(
            {
                "title": title,
                "active_attachment_ids": attachment_ids,
            }
        )
        .eq("user_id", user_id)
        .eq("id", chat_id)
        .execute()
    )


def update_chat_context(
    client: Client, user_id: str, chat_id: str, attachment_ids: list[str]
) -> None:
    (
        client.table("chats")
        .update({"active_attachment_ids": attachment_ids})
        .eq("user_id", user_id)
        .eq("id", chat_id)
        .execute()
    )


def add_message(
    client: Client,
    user_id: str,
    chat_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    result = (
        client.table("messages")
        .insert(
            {
                "user_id": user_id,
                "chat_id": chat_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        )
        .execute()
    )
    return result.data[0]


def save_attachment(
    client: Client,
    user_id: str,
    chat_id: str,
    message_id: str,
    attachment: PreparedAttachment,
) -> dict:
    attachment_id = str(uuid4())
    extension = attachment.file_name.rsplit(".", 1)[-1].lower()
    path = f"{user_id}/{chat_id}/{attachment_id}.{extension}"
    storage = client.storage.from_(ATTACHMENT_BUCKET)
    storage.upload(
        path=path,
        file=attachment.data,
        file_options={
            "content-type": attachment.mime_type,
            "upsert": "false",
        },
    )
    result = (
        client.table("attachments")
        .insert(
            {
                "id": attachment_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "file_name": attachment.file_name,
                "mime_type": attachment.mime_type,
                "size_bytes": len(attachment.data),
                "storage_path": path,
                "extracted_text": attachment.extracted_text,
            }
        )
        .execute()
    )
    return result.data[0]


def load_chat_messages(client: Client, user_id: str, chat_id: str) -> list[dict]:
    message_result = (
        client.table("messages")
        .select("id,role,content,metadata,created_at")
        .eq("user_id", user_id)
        .eq("chat_id", chat_id)
        .order("created_at")
        .execute()
    )
    attachment_result = (
        client.table("attachments")
        .select("id,message_id,file_name,mime_type,extracted_text")
        .eq("user_id", user_id)
        .eq("chat_id", chat_id)
        .execute()
    )
    attachments_by_message: dict[str, list[dict]] = {}
    for attachment in attachment_result.data:
        attachments_by_message.setdefault(attachment["message_id"], []).append(
            attachment
        )

    messages = []
    for row in message_result.data:
        messages.append(
            {
                **row,
                "metadata": row.get("metadata") or {},
                "attachments": attachments_by_message.get(row["id"], []),
            }
        )
    return messages


def load_active_attachments(
    client: Client, user_id: str, chat_id: str, attachment_ids: list[str]
) -> list[dict]:
    if not attachment_ids:
        return []
    result = (
        client.table("attachments")
        .select("id,file_name,mime_type,storage_path,extracted_text")
        .eq("user_id", user_id)
        .eq("chat_id", chat_id)
        .in_("id", attachment_ids)
        .execute()
    )
    attachments = []
    for row in result.data:
        attachment = {**row, "image_bytes": b""}
        if row["mime_type"].startswith("image/"):
            attachment["image_bytes"] = client.storage.from_(
                ATTACHMENT_BUCKET
            ).download(row["storage_path"])
        attachments.append(attachment)
    return attachments
