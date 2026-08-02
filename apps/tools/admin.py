from django.contrib import admin
from .models import (
    IPLookupLog, IPCache, DevToolLog, AIToolRequest,
    TextToolLog, FinanceCalculation, BusinessToolLog,
    FileToolLog, ToolAnalytics,
)


@admin.register(IPLookupLog)
class IPLookupLogAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'query', 'ip_address', 'success', 'result_cached', 'duration_ms', 'created_at')
    list_filter   = ('tool', 'success', 'result_cached')
    search_fields = ('query', 'ip_address')
    readonly_fields = ('id', 'created_at')


@admin.register(IPCache)
class IPCacheAdmin(admin.ModelAdmin):
    list_display  = ('ip', 'hits', 'cached_at')
    search_fields = ('ip',)
    readonly_fields = ('cached_at',)


@admin.register(DevToolLog)
class DevToolLogAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'input_size', 'output_size', 'success', 'duration_ms', 'created_at')
    list_filter   = ('tool', 'success')
    readonly_fields = ('id', 'created_at')


@admin.register(AIToolRequest)
class AIToolRequestAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'model_used', 'total_tokens', 'success', 'duration_ms', 'created_at')
    list_filter   = ('tool', 'model_used', 'success')
    readonly_fields = ('id', 'created_at')
    search_fields = ('output_preview',)


@admin.register(TextToolLog)
class TextToolLogAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'input_size', 'success', 'created_at')
    list_filter   = ('tool',)
    readonly_fields = ('id', 'created_at')


@admin.register(FinanceCalculation)
class FinanceCalculationAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'currency', 'success', 'created_at')
    list_filter   = ('tool', 'currency')
    readonly_fields = ('id', 'created_at')


@admin.register(BusinessToolLog)
class BusinessToolLogAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'currency', 'success', 'created_at')
    list_filter   = ('tool',)
    readonly_fields = ('id', 'created_at')


@admin.register(FileToolLog)
class FileToolLogAdmin(admin.ModelAdmin):
    list_display  = ('tool', 'file_count', 'input_size', 'output_size', 'savings_pct', 'success', 'created_at')
    list_filter   = ('tool', 'success')
    readonly_fields = ('id', 'created_at')


@admin.register(ToolAnalytics)
class ToolAnalyticsAdmin(admin.ModelAdmin):
    list_display  = ('date', 'tool_name', 'category', 'total_uses', 'unique_ips', 'errors')
    list_filter   = ('category', 'date')
    search_fields = ('tool_name',)
    ordering      = ('-date', '-total_uses')
