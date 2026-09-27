from django.contrib import admin
from .models import Team, TeamMembership, Invite


class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 1
    autocomplete_fields = ['user']


class InviteInline(admin.TabularInline):
    model = Invite
    extra = 0
    readonly_fields = ('token', 'created_at', 'used_at')
    fields = ('token', 'email', 'expires_at', 'used_at', 'created_by')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'created_by', 'created_at')
    list_filter = ('event',)
    search_fields = ('name', 'event__name', 'created_by__username')
    autocomplete_fields = ['created_by', 'event']
    inlines = [TeamMembershipInline, InviteInline]


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ('team', 'user', 'role', 'joined_at')
    list_filter = ('role', 'team__event')
    search_fields = ('team__name', 'user__username', 'team__event__name')
    autocomplete_fields = ['team', 'user']


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ('team', 'email', 'created_by', 'expires_at', 'used_at', 'is_valid')
    list_filter = ('team__event',)
    search_fields = ('team__name', 'email', 'token')
    readonly_fields = ('token', 'created_at')
