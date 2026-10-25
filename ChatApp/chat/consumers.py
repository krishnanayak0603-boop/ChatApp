import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .models import ChatRoom, Message

# Online users ki list (memory mein). Format:
# { "room-slug": { "channel_name": (user_id, username) } }
ONLINE_USERS = {}


def get_online_list(room_slug):
    unique = {}
    for user_id, username in ONLINE_USERS.get(room_slug, {}).values():
        unique[user_id] = username

    return [
        {"user_id": user_id, "username": username}
        for user_id, username in sorted(
            unique.items(), key=lambda item: item[1].lower()
        )
    ]


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_slug = self.scope["url_route"]["kwargs"]["slug"]
        self.room_group_name = f"chat_{self.room_slug}"

        if not await self.room_exists():
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()
        print("CHAT CONNECTED:", self.user.username, self.room_slug)

        # Is user ko online list mein daalo aur sabko batao.
        ONLINE_USERS.setdefault(self.room_slug, {})[self.channel_name] = (
            self.user.id,
            self.user.username,
        )
        await self.broadcast_presence()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            room_users = ONLINE_USERS.get(self.room_slug, {})
            room_users.pop(self.channel_name, None)

            if not room_users:
                ONLINE_USERS.pop(self.room_slug, None)

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            await self.broadcast_presence()

    async def broadcast_presence(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "presence_update",
                "users": get_online_list(self.room_slug),
            },
        )

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "")
        except (json.JSONDecodeError, TypeError):
            await self.send(text_data=json.dumps({
                "error": "Invalid message format."
            }))
            return

        if not isinstance(data, dict):
            await self.send(text_data=json.dumps({
                "error": "Message must be a JSON object."
            }))
            return

        # ---- Typing event (message save nahi hota) ----
        if data.get("type") == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_event",
                    "sender_channel_name": self.channel_name,
                    "user_id": self.user.id,
                    "username": self.user.username,
                    "is_typing": bool(data.get("is_typing")),
                },
            )
            return

        if data.get("type") == "sync_messages":
            after_id = data.get("after_id")
            if (
                isinstance(after_id, bool)
                or not isinstance(after_id, int)
                or after_id < 0
            ):
                await self.send(text_data=json.dumps({
                    "error": "after_id must be a non-negative integer."
                }))
                return

            sync_result = await self.get_messages_after(after_id)
            await self.send(text_data=json.dumps({
                "type": "message_sync",
                **sync_result,
            }))
            return

        # ---- Normal message (pehle jaisa hi) ----
        content = data.get("message", "")

        if not isinstance(content, str):
            await self.send(text_data=json.dumps({
                "error": "Message must be text."
            }))
            return

        content = content.strip()

        if not content or len(content) > 5000:
            await self.send(text_data=json.dumps({
                "error": "Message must contain 1 to 5000 characters."
            }))
            return

        try:
            saved_message = await self.save_message(content)

            if saved_message is None:
                await self.send(text_data=json.dumps({
                    "error": "Room not found. Please refresh."
                }))
                return

            print("MESSAGE SAVED:", saved_message)

            # Step A: Confirm directly to the sender.
            await self.send(text_data=json.dumps(saved_message))

            # Step B: Broadcast to other users in the same room.
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "sender_channel_name": self.channel_name,
                    "data": saved_message,
                },
            )

        except Exception as exc:
            print("CHAT MESSAGE ERROR:", repr(exc))

            await self.send(text_data=json.dumps({
                "error": "Server could not process the message. Check the Django terminal."
            }))

    async def chat_message(self, event):
        # Sender already received direct confirmation.
        if event.get("sender_channel_name") == self.channel_name:
            return

        await self.send(text_data=json.dumps(event["data"]))

    async def typing_event(self, event):
        # Apni typing khud ko mat dikhao.
        if event.get("sender_channel_name") == self.channel_name:
            return

        await self.send(text_data=json.dumps({
            "type": "typing",
            "user_id": event["user_id"],
            "username": event["username"],
            "is_typing": event["is_typing"],
        }))

    async def presence_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "presence",
            "users": event["users"],
        }))

    @database_sync_to_async
    def room_exists(self):
        return ChatRoom.objects.filter(
            slug=self.room_slug
        ).exists()

    @database_sync_to_async
    def save_message(self, content):
        room = ChatRoom.objects.filter(
            slug=self.room_slug
        ).first()

        if room is None:
            return None

        message = Message.objects.create(
            room=room,
            sender=self.user,
            content=content,
        )

        timestamp = timezone.localtime(message.timestamp)

        return {
            "id": message.id,
            "message": message.content,
            "username": self.user.username,
            "user_id": self.user.id,
            "timestamp": (
                f"{timestamp:%b %d, %Y} · "
                f"{timestamp.hour % 12 or 12}:{timestamp:%M %p}"
            ),
        }

    @database_sync_to_async
    def get_messages_after(self, after_id):
        messages = list(
            Message.objects.filter(
                room__slug=self.room_slug,
                id__gt=after_id,
            )
            .select_related("sender")
            .order_by("id")[:201]
        )
        has_more = len(messages) > 200
        messages = messages[:200]

        serialized_messages = []
        for message in messages:
            timestamp = timezone.localtime(message.timestamp)
            serialized_messages.append({
                "id": message.id,
                "message": message.content,
                "username": message.sender.username,
                "user_id": message.sender_id,
                "timestamp": (
                    f"{timestamp:%b %d, %Y} · "
                    f"{timestamp.hour % 12 or 12}:{timestamp:%M %p}"
                ),
            })

        return {
            "messages": serialized_messages,
            "has_more": has_more,
            "next_after_id": (
                serialized_messages[-1]["id"] if serialized_messages else after_id
            ),
        }