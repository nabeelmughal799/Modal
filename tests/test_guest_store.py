import unittest

from attachments import PreparedAttachment
from guest_store import (
    add_guest_message,
    create_guest_chat,
    list_guest_chats,
    load_guest_active_attachments,
    save_guest_attachment,
)


class GuestStoreTests(unittest.TestCase):
    def test_new_chats_have_separate_messages_and_attachment_context(self):
        chats = {}
        first = create_guest_chat(chats, "First chat")
        second = create_guest_chat(chats, "Second chat")
        message = add_guest_message(first, "user", "Review this image")
        attachment = save_guest_attachment(
            first,
            message["id"],
            PreparedAttachment(
                "chairs.png",
                "image/png",
                b"image bytes",
            ),
        )

        self.assertEqual(list_guest_chats(chats)[0]["id"], first["id"])
        self.assertEqual(
            first["messages"][0]["attachments"][0]["file_name"], "chairs.png"
        )
        self.assertEqual(
            load_guest_active_attachments(first, [attachment["id"]])[0]["image_bytes"],
            b"image bytes",
        )
        self.assertEqual(second["messages"], [])
        self.assertEqual(load_guest_active_attachments(second, [attachment["id"]]), [])


if __name__ == "__main__":
    unittest.main()
