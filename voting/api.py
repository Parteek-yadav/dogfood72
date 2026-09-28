"""
DRF API views for Community Voting and Comments.
"""

import hashlib
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count
from rest_framework import permissions, status, exceptions
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from submissions.models import Submission
from core.models import AuditLogEntry
from .models import Vote, Comment
from .serializers import (
    VoteSerializer,
    VoteCastSerializer,
    VoteSummarySerializer,
    CommentSerializer,
    CommentCreateSerializer,
)


class VoteCastAPIView(APIView):
    """
    POST /api/submissions/{pk}/vote/
    Cast a public or participant vote on a project submission.
    Reconciles authenticated user votes with anonymous signed voter tokens.
    Prevents duplicate votes via dual database constraints.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Cast a vote for a project submission",
        request=VoteCastSerializer,
        responses={201: VoteSerializer}
    )
    def post(self, request, pk):
        submission = get_object_or_404(Submission.objects.select_related('event'), pk=pk)
        event = submission.event

        # Check voting window
        now = timezone.now()
        if event.voting_start and now < event.voting_start:
            raise exceptions.ValidationError({'detail': "Voting for this event has not opened yet."})
        if event.voting_end and now > event.voting_end:
            raise exceptions.ValidationError({'detail': "Voting for this event has closed."})

        serializer = VoteCastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user if request.user.is_authenticated else None
        voter_token = serializer.validated_data.get('voter_token') or None
        weight = serializer.validated_data.get('weight', Decimal('1.00'))

        if not user and not voter_token:
            raise exceptions.ValidationError({'detail': "A vote requires either an authenticated user or a signed voter token."})

        # Check existing votes
        if user and Vote.objects.filter(submission=submission, user=user).exists():
            raise exceptions.ValidationError({'detail': "You have already cast a vote for this submission."})
        if voter_token and Vote.objects.filter(submission=submission, voter_token=voter_token).exists():
            raise exceptions.ValidationError({'detail': "This voter token has already been used for this submission."})

        # Hash IP address
        ip_addr = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        ip_hash = hashlib.sha256(ip_addr.encode('utf-8')).hexdigest() if ip_addr else ''

        vote = Vote.objects.create(
            submission=submission,
            user=user,
            voter_token=voter_token,
            weight=weight,
            ip_hash=ip_hash
        )

        AuditLogEntry.log('vote.cast', submission, actor=user, metadata={'vote_id': vote.id, 'weight': str(weight)})
        return Response(VoteSerializer(vote).data, status=status.HTTP_201_CREATED)


class VoteSummaryAPIView(APIView):
    """
    GET /api/submissions/{pk}/votes/
    Retrieve aggregate voting statistics for a submission.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Retrieve aggregate vote count and weight for a submission",
        responses={200: VoteSummarySerializer}
    )
    def get(self, request, pk):
        submission = get_object_or_404(Submission, pk=pk)
        stats = submission.votes.aggregate(
            total_votes=Count('id'),
            total_weight=Sum('weight')
        )
        return Response({
            'submission_id': submission.id,
            'total_votes': stats['total_votes'] or 0,
            'total_weight': stats['total_weight'] or Decimal('0.00'),
        }, status=status.HTTP_200_OK)


class CommentListCreateAPIView(APIView):
    """
    GET /api/submissions/{pk}/comments/
    List discussion comments on a project submission.

    POST /api/submissions/{pk}/comments/
    Post a new discussion comment (authenticated user required).
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="List comments for a project submission",
        responses={200: CommentSerializer(many=True)}
    )
    def get(self, request, pk):
        submission = get_object_or_404(Submission, pk=pk)
        comments = submission.comments.select_related('user').all()
        return Response(CommentSerializer(comments, many=True).data)

    @extend_schema(
        summary="Post a comment on a project submission",
        request=CommentCreateSerializer,
        responses={201: CommentSerializer}
    )
    def post(self, request, pk):
        submission = get_object_or_404(Submission, pk=pk)
        serializer = CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = Comment.objects.create(
            submission=submission,
            user=request.user,
            body=serializer.validated_data['body']
        )
        AuditLogEntry.log('comment.created', submission, actor=request.user, metadata={'comment_id': comment.id})
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
