from django.contrib import admin
from .models import ChatUser, Conversation, Message, Project, ProjectAnalysis


@admin.register(ChatUser)
class ChatUserAdmin(admin.ModelAdmin):
    list_display  = ('session_id', 'name', 'email', 'company', 'created_at')
    search_fields = ('session_id', 'email', 'name')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'phase', 'status', 'intent', 'created_at')
    list_filter   = ('status', 'phase', 'intent')
    search_fields = ('id', 'user__session_id')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ('conversation', 'role', 'content_preview', 'created_at')
    list_filter   = ('role',)

    def content_preview(self, obj):
        return obj.content[:80]
    content_preview.short_description = 'Content'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'project_type', 'complexity', 'status', 'timeline_weeks', 'created_at')
    list_filter  = ('status', 'complexity')


@admin.register(ProjectAnalysis)
class ProjectAnalysisAdmin(admin.ModelAdmin):
    list_display = ('project', 'feasibility', 'created_at')
