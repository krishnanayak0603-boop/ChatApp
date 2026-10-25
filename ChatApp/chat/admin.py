
from django.contrib import admin
from .models import ChatRoom, Message


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "room", "timestamp")
    search_fields = ("content", "sender__username")
    list_filter = ("room", "timestamp")
