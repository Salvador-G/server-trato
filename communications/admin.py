from django.contrib import admin
from .models import Conversation, Message, MessageAttachment

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_workflow", "channel", "updated_at")
    list_filter = ("channel",)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "direction", "subject", "status", "created_at")
    list_filter = ("direction", "status")
    search_fields = ("subject", "from_address", "to_address")

@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "created_at")