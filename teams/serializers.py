"""
DRF Serializers for Teams, Team Memberships, and Invites.
"""

from rest_framework import serializers
from .models import Team, TeamMembership, Invite


class TeamMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = TeamMembership
        fields = ['id', 'user_id', 'username', 'email', 'role', 'joined_at']


class InviteSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Invite
        fields = ['id', 'token', 'email', 'expires_at', 'used_at', 'is_expired', 'created_by_username', 'created_at']


class InviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True, help_text="Optional target email to restrict invite")
    expires_in_days = serializers.IntegerField(default=7, min_value=1, max_value=30, help_text="Days until invite expires")


class TeamDetailSerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source='event.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    memberships = TeamMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = [
            'id', 'event', 'event_name', 'name', 'created_by', 'created_by_username',
            'memberships', 'created_at', 'updated_at'
        ]


class TeamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['name']
