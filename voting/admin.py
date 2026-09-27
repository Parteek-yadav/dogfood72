from django.contrib import admin
from .models import Vote, Comment


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('submission', 'user', 'voter_token', 'weight', 'created_at')
    list_filter = ('created_at', 'submission__event')
    search_fields = ('submission__title', 'user__username', 'voter_token')
    autocomplete_fields = ['submission', 'user']
    readonly_fields = ('created_at',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('submission', 'user', 'created_at', 'short_body')
    list_filter = ('created_at', 'submission__event')
    search_fields = ('submission__title', 'user__username', 'body')
    autocomplete_fields = ['submission', 'user']

    def short_body(self, obj):
        return (obj.body[:50] + '...') if len(obj.body) > 50 else obj.body
    short_body.short_description = "Comment Preview"
