"""
Django REST Framework serializers for Judging API endpoints.
"""

from decimal import Decimal
from rest_framework import serializers
from django.contrib.auth.models import User
from submissions.models import Submission
from judging.models import Rubric, RubricCriterion, JudgeAssignment, Score, NormalizedScore


class RubricCriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RubricCriterion
        fields = ['id', 'name', 'description', 'weight', 'order']


class RubricSerializer(serializers.ModelSerializer):
    criteria = RubricCriterionSerializer(many=True, read_only=True)
    total_weight = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = Rubric
        fields = ['id', 'event', 'name', 'description', 'criteria', 'total_weight', 'created_at']


class RubricCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rubric
        fields = ['name', 'description']


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


class JudgeProgressItemSerializer(serializers.Serializer):
    judge_id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    assigned_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    in_progress_count = serializers.IntegerField()
    unstarted_count = serializers.IntegerField()
    last_activity = serializers.CharField(allow_null=True)


class JudgeProgressSummarySerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    event_name = serializers.CharField()
    total_judges = serializers.IntegerField()
    total_assignments = serializers.IntegerField()
    completed_assignments = serializers.IntegerField()
    progress_percent = serializers.FloatField()
    judges = JudgeProgressItemSerializer(many=True)


class JudgeScoreItemSerializer(serializers.Serializer):
    submission_id = serializers.IntegerField()
    submission_title = serializers.CharField()
    criterion = serializers.CharField()
    value = serializers.IntegerField()
    feedback = serializers.CharField(allow_blank=True)


class AlgorithmicAssignmentRequestSerializer(serializers.Serializer):
    k = serializers.IntegerField(default=3, min_value=1, max_value=20, help_text="Number of judges per submission")


class AlgorithmicAssignmentResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    assignments_generated = serializers.IntegerField()
    k = serializers.IntegerField()


class ManualAssignmentSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['add', 'delete'], help_text="Action to execute")
    judge_id = serializers.IntegerField(required=False, allow_null=True)
    submission_id = serializers.IntegerField(required=False, allow_null=True)
    assignment_id = serializers.IntegerField(required=False, allow_null=True)


class ScoreInputItemSerializer(serializers.Serializer):
    criterion_id = serializers.IntegerField(help_text="ID of RubricCriterion")
    value = serializers.IntegerField(min_value=1, max_value=5, help_text="Integer score between 1 and 5")
    feedback = serializers.CharField(required=False, allow_blank=True, default="", help_text="Optional feedback note")


class ScoreSubmissionRequestSerializer(serializers.Serializer):
    scores = ScoreInputItemSerializer(many=True, help_text="List of criterion score evaluations")


class ScoreSubmissionResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    assignment_status = serializers.CharField()
    scores_saved = serializers.IntegerField()


class NormalizationTriggerSerializer(serializers.Serializer):
    method = serializers.CharField(required=False, default='zscore', help_text="Normalization algorithm (default: 'zscore')")


class NormalizationResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField(required=False)
    submission_count = serializers.IntegerField(required=False)
    judge_count = serializers.IntegerField(required=False)
