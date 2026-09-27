from django.contrib import admin
from .models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'target_type', 'target_id')
    list_filter = ('action', 'target_type', 'created_at')
    search_fields = ('action', 'target_type', 'target_id', 'actor__username')
    readonly_fields = ('created_at', 'actor', 'action', 'target_type', 'target_id', 'metadata')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
