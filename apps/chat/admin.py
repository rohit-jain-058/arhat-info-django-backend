from django.contrib import admin
from .models import ChatUser, Conversation, Message

@admin.register(ChatUser)
class ChatUserAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'name', 'email', 'created_at')

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'phase', 'created_at')
    list_filter  = ('phase',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'role', 'agent_name', 'created_at')
    list_filter  = ('role', 'agent_name')
