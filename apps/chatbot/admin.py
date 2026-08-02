from django.contrib import admin
from .models import ChatSession, ChatMessage


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display  = ('session_id', 'phase', 'created_at', 'updated_at')
    list_filter   = ('phase',)
    search_fields = ('session_id',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display  = ('session', 'role', 'agent', 'preview', 'created_at')
    list_filter   = ('role', 'agent')
    search_fields = ('content',)

    def preview(self, obj):
        return obj.content[:80]
    preview.short_description = 'Content'
