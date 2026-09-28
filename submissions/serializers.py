"""
DRF Serializers for Project Submissions, Versions, and Gallery Images.
"""

from rest_framework import serializers
from .models import Submission, SubmissionImage, SubmissionVersion


class SubmissionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionImage
        fields = ['id', 'image', 'caption', 'order']


class SubmissionImageUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionImage
        fields = ['image', 'caption', 'order']


class SubmissionSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)
    event_name = serializers.CharField(source='event.name', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True, default=None)
    gallery_images = SubmissionImageSerializer(many=True, read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'team', 'team_name', 'event', 'event_name', 'track', 'track_name',
            'title', 'tagline', 'description', 'thumbnail', 'repo_url', 'live_url',
            'demo_video_url', 'tech_tags', 'custom_answers', 'status',
            'created_at', 'updated_at', 'submitted_at', 'gallery_images'
        ]


class SubmissionCreateSerializer(serializers.ModelSerializer):
    tech_tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        help_text="List of tech tags, e.g. [\"Python\", \"React\"]"
    )
    custom_answers = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        default=dict,
        help_text="Custom question answers keyed by str(question_id)"
    )

    class Meta:
        model = Submission
        fields = [
            'title', 'tagline', 'description', 'track', 'repo_url',
            'live_url', 'demo_video_url', 'tech_tags', 'custom_answers'
        ]


class SubmissionUpdateSerializer(serializers.ModelSerializer):
    action = serializers.ChoiceField(
        choices=['save_draft', 'submit_final'],
        default='save_draft',
        required=False,
        help_text="Action: 'save_draft' to save in-progress draft, 'submit_final' to submit for judging"
    )
    tech_tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list
    )
    custom_answers = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        default=dict
    )

    class Meta:
        model = Submission
        fields = [
            'title', 'tagline', 'description', 'track', 'repo_url',
            'live_url', 'demo_video_url', 'tech_tags', 'custom_answers', 'action'
        ]
