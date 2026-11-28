import unittest
from types import SimpleNamespace

from chat_store import chat_title, list_chats, load_chat_messages


class Query:
    def __init__(self, table_name, calls):
        self.table_name = table_name
        self.calls = calls

    def select(self, columns):
        self.calls.append((self.table_name, "select", columns))
        return self

    def eq(self, column, value):
        self.calls.append((self.table_name, "eq", column, value))
        return self

    def order(self, column, desc=False):
        self.calls.append((self.table_name, "order", column, desc))
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class FakeClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return Query(name, self.calls)


class ChatStoreTests(unittest.TestCase):
    def test_titles_use_the_first_message_or_file_name(self):
        self.assertEqual(chat_title("  Explain   this  ", []), "Explain this")
        self.assertEqual(chat_title("", ["report.pdf"]), "File: report.pdf")

    def test_chat_queries_are_scoped_to_the_authenticated_user(self):
        client = FakeClient()
        list_chats(client, "user-a")
        filters = [call for call in client.calls if call[1] == "eq"]
        self.assertIn(("chats", "eq", "user_id", "user-a"), filters)

    def test_message_restore_is_scoped_to_user_and_chat(self):
        client = FakeClient()
        load_chat_messages(client, "user-a", "chat-a")
        filters = [call for call in client.calls if call[1] == "eq"]
        self.assertIn(("messages", "eq", "user_id", "user-a"), filters)
        self.assertIn(("messages", "eq", "chat_id", "chat-a"), filters)
        self.assertIn(("attachments", "eq", "user_id", "user-a"), filters)
        self.assertIn(("attachments", "eq", "chat_id", "chat-a"), filters)


if __name__ == "__main__":
    unittest.main()
