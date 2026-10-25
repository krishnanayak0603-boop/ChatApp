from urllib.parse import urlparse

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, TransactionTestCase

from .models import ChatRoom, Message
from .routing import websocket_urlpatterns


class ChatPageTests(TestCase):
    def test_signup_login_room_access_and_logout(self):
        ChatRoom.objects.create(name="Python Learners", slug="python-learners")

        anonymous_response = self.client.get("/room/python-learners/")
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn("/login/", anonymous_response.url)

        signup_response = self.client.post("/signup/", {
            "username": "connectly_auth_test",
            "password1": "DemoPass!Connectly26",
            "password2": "DemoPass!Connectly26",
        })
        self.assertRedirects(signup_response, "/")
        self.assertEqual(self.client.get("/room/python-learners/").status_code, 200)

        logout_response = self.client.post("/logout/")
        self.assertRedirects(logout_response, "/login/")
        anonymous_response = self.client.get("/room/python-learners/")
        self.assertEqual(anonymous_response.status_code, 302)

        login_response = self.client.post("/login/", {
            "username": "connectly_auth_test",
            "password": "DemoPass!Connectly26",
        })
        self.assertRedirects(login_response, "/")
        self.assertEqual(self.client.get("/room/python-learners/").status_code, 200)

    def test_room_page_renders_saved_message(self):
        user = User.objects.create_user(username="alice", password="password")
        room = ChatRoom.objects.create(name="Python Learners", slug="python-learners")
        message = Message.objects.create(
            room=room,
            sender=user,
            content="A saved message",
        )
        self.client.force_login(user)

        response = self.client.get("/room/python-learners/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-message-id="{message.id}"')
        self.assertContains(response, "A saved message")


class ChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            password="password",
        )
        self.second_user = User.objects.create_user(
            username="bob",
            password="password",
        )
        self.room = ChatRoom.objects.create(
            name="Python Learners",
            slug="python-learners",
        )

    async def connect(self, user=None):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/chat/{self.room.slug}/",
        )
        communicator.scope["user"] = user or self.user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()
        return communicator

    async def test_sync_messages_returns_paginated_id_based_history(self):
        messages = await database_sync_to_async(Message.objects.bulk_create)([
            Message(room=self.room, sender=self.user, content=f"Message {index}")
            for index in range(201)
        ])
        message_ids = [message.id for message in messages]
        communicator = await self.connect()

        try:
            await communicator.send_json_to({
                "type": "sync_messages",
                "after_id": 0,
            })
            first_page = await communicator.receive_json_from()

            self.assertEqual(first_page["type"], "message_sync")
            self.assertEqual(
                [message["id"] for message in first_page["messages"]],
                message_ids[:200],
            )
            self.assertTrue(first_page["has_more"])
            self.assertEqual(first_page["next_after_id"], message_ids[199])

            await communicator.send_json_to({
                "type": "sync_messages",
                "after_id": first_page["next_after_id"],
            })
            second_page = await communicator.receive_json_from()

            self.assertEqual(
                [message["id"] for message in second_page["messages"]],
                message_ids[200:],
            )
            self.assertFalse(second_page["has_more"])
        finally:
            await communicator.disconnect()

    async def test_two_users_receive_presence_typing_and_live_messages(self):
        first = await self.connect(self.user)
        second = None

        try:
            second = await self.connect(self.second_user)
            first_presence = await first.receive_json_from()
            self.assertEqual(first_presence["type"], "presence")
            self.assertEqual(
                {user["username"] for user in first_presence["users"]},
                {"alice", "bob"},
            )

            await first.send_json_to({
                "type": "typing",
                "is_typing": True,
            })
            typing = await second.receive_json_from()
            self.assertEqual(typing["type"], "typing")
            self.assertEqual(typing["username"], "alice")
            self.assertTrue(typing["is_typing"])

            await first.send_json_to({"message": "Live between users"})
            sender_confirmation = await first.receive_json_from()
            recipient_message = await second.receive_json_from()
            self.assertEqual(sender_confirmation["id"], recipient_message["id"])
            self.assertEqual(recipient_message["message"], "Live between users")
            self.assertEqual(recipient_message["username"], "alice")

            await first.disconnect()
            first = None
            remaining_presence = await second.receive_json_from()
            self.assertEqual(remaining_presence["type"], "presence")
            self.assertEqual(
                [user["username"] for user in remaining_presence["users"]],
                ["bob"],
            )
        finally:
            if first is not None:
                await first.disconnect()
            if second is not None:
                await second.disconnect()

    async def test_non_object_and_invalid_sync_cursor_return_errors(self):
        communicator = await self.connect()

        try:
            await communicator.send_json_to([])
            self.assertIn(
                "error",
                await communicator.receive_json_from(),
            )

            await communicator.send_json_to({
                "type": "sync_messages",
                "after_id": -1,
            })
            response = await communicator.receive_json_from()
            self.assertIn("after_id", response["error"])
        finally:
            await communicator.disconnect()

    async def test_unauthenticated_user_cannot_connect(self):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/chat/{self.room.slug}/",
        )
        communicator.scope["user"] = AnonymousUser()

        connected, _ = await communicator.connect()

        self.assertFalse(connected)

    async def test_authenticated_websocket_validates_origin(self):
        origin_validated_router = AllowedHostsOriginValidator(
            URLRouter(websocket_urlpatterns)
        )
        untrusted = WebsocketCommunicator(
            origin_validated_router,
            f"/ws/chat/{self.room.slug}/",
            headers=[(b"origin", b"https://attacker.example")],
        )
        untrusted.scope["user"] = self.user
        connected, _ = await untrusted.connect()
        self.assertFalse(connected)
        self.assertTrue(
            origin_validated_router.valid_origin(urlparse("http://testserver"))
        )

    async def test_live_message_confirmation_includes_database_id(self):
        communicator = await self.connect()

        try:
            await communicator.send_json_to({"message": "Hello"})
            response = await communicator.receive_json_from()

            self.assertEqual(response["message"], "Hello")
            self.assertGreater(response["id"], 0)
            self.assertEqual(response["user_id"], self.user.id)
        finally:
            await communicator.disconnect()
