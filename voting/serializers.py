"""
DRF Serializers for Voting and Community Comments.
"""

from decimal import Decimal
from rest_framework import serializers
from .models import Vote, Comment


class VoteSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = Vote
        fields = ['id', 'submission', 'user', 'username', 'voter_token', 'weight', 'created_at']


class VoteCastSerializer(serializers.Serializer):
    voter_token = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=64,
        help_text="Signed browser token for anonymous voter reconciliation (omitted if user is authenticated)"
    )
    weight = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Vote credit weight (default 1.00; allows quadratic voting calculations)"
    )


class VoteSummarySerializer(serializers.Serializer):
    submission_id = serializers.IntegerField()
    total_votes = serializers.IntegerField()
    total_weight = serializers.DecimalField(max_digits=10, decimal_places=2)


class CommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'submission', 'user', 'username', 'body', 'created_at', 'updated_at']


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['body']
