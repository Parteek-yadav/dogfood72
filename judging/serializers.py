"""
Django REST Framework serializers for Judging API endpoints.
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from submissions.models import Submission
from judging.models import JudgeAssignment, Score, RubricCriterion


class ScoreSerializer(serializers.ModelSerializer):
    criterion_name = serializers.CharField(source='criterion.name', read_only=True)

    class Meta:
        model = Score
        fields = ['id', 'criterion', 'criterion_name', 'value', 'feedback', 'created_at', 'updated_at']


class SubmissionBriefSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True, default=None)

    class Meta:
        model = Submission
        fields = ['id', 'title', 'tagline', 'repo_url', 'live_url', 'demo_video_url', 'team_name', 'track_name']


class MyAssignmentSerializer(serializers.ModelSerializer):
    submission = SubmissionBriefSerializer(read_only=True)
    my_scores = ScoreSerializer(source='scores', many=True, read_only=True)

    class Meta:
        model = JudgeAssignment
        fields = ['id', 'submission', 'status', 'assigned_at', 'completed_at', 'my_scores']


class OrganizerSubmissionScoreSerializer(serializers.ModelSerializer):
    judge_id = serializers.IntegerField(source='judge.id', read_only=True)
    judge_username = serializers.CharField(source='judge.username', read_only=True)
    scores = ScoreSerializer(many=True, read_only=True)

    class Meta:
        model = JudgeAssignment
        fields = ['id', 'judge_id', 'judge_username', 'status', 'assigned_at', 'completed_at', 'scores']
