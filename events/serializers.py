"""
DRF Serializers for Event management and sub-resources.
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Event, EventRole, Track, Prize, CustomQuestion


class TrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Track
        fields = ['id', 'name', 'description']


class PrizeSerializer(serializers.ModelSerializer):
    track_name = serializers.CharField(source='track.name', read_only=True, default=None)

    class Meta:
        model = Prize
        fields = ['id', 'name', 'track', 'track_name', 'amount', 'description', 'rank']


class CustomQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomQuestion
        fields = ['id', 'label', 'field_type', 'required', 'order', 'choices']


class EventRoleSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = EventRole
        fields = ['id', 'user', 'username', 'email', 'role', 'assigned_at']


class EventRoleCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(help_text="ID of User to assign role to")
    role = serializers.ChoiceField(choices=EventRole.Role.choices, help_text="Role: organizer, judge, participant")


class EventListSerializer(serializers.ModelSerializer):
    organizer_username = serializers.CharField(source='organizer.username', read_only=True)
    tracks_count = serializers.IntegerField(source='tracks.count', read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'slug', 'description', 'start_date', 'end_date',
            'submission_deadline', 'voting_start', 'voting_end',
            'is_published', 'organizer_username', 'tracks_count', 'created_at'
        ]


class EventDetailSerializer(serializers.ModelSerializer):
    organizer_username = serializers.CharField(source='organizer.username', read_only=True)
    tracks = TrackSerializer(many=True, read_only=True)
    prizes = PrizeSerializer(many=True, read_only=True)
    custom_questions = CustomQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'slug', 'description', 'start_date', 'end_date',
            'submission_deadline', 'voting_start', 'voting_end',
            'is_published', 'organizer', 'organizer_username',
            'tracks', 'prizes', 'custom_questions', 'created_at', 'updated_at'
        ]


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False)

    class Meta:
        model = Event
        fields = [
            'name', 'slug', 'description', 'start_date', 'end_date',
            'submission_deadline', 'voting_start', 'voting_end', 'is_published'
        ]
