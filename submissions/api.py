"""
DRF API views for Submissions, Edits, Deadline Guards, and Gallery Images.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import ValidationError
from rest_framework import generics, permissions, status, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from core.models import AuditLogEntry
from core.permissions import is_team_member, is_event_organizer
from events.models import Event
from teams.models import Team
from .models import Submission, SubmissionImage
from .serializers import (
    SubmissionSerializer,
    SubmissionCreateSerializer,
    SubmissionUpdateSerializer,
    SubmissionImageSerializer,
    SubmissionImageUploadSerializer,
)


class EventSubmissionListAPIView(APIView):
    """
    GET /api/events/{event_id}/submissions/
    Public gallery listing submitted projects for an event.
    Supports filtering by search query (?q=) and challenge track (?track=).
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="List submitted projects for an event",
        parameters=[
            OpenApiParameter(name='q', description='Search text for title, tagline, or tech tags', required=False, type=str),
            OpenApiParameter(name='track', description='Filter by track ID', required=False, type=int),
        ],
        responses={200: SubmissionSerializer(many=True)}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)

        # Check published status
        if not event.is_published and not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Event is not published.")

        qs = (
            Submission.objects.filter(event=event, status=Submission.Status.SUBMITTED)
            .select_related('team', 'track')
            .prefetch_related('gallery_images')
        )

        query = request.query_params.get('q', '').strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(tagline__icontains=query) |
                Q(tech_tags__icontains=query)
            )

        track_id = request.query_params.get('track', '').strip()
        if track_id:
            qs = qs.filter(track_id=track_id)

        return Response(SubmissionSerializer(qs, many=True).data)


class TeamSubmissionCreateAPIView(APIView):
    """
    POST /api/teams/{team_id}/submissions/
    Create initial draft project submission for a team.
    Checks:
    - User is team member
    - Submission deadline has not passed
    - Team does not already have an active submission
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Create initial draft submission for a team",
        request=SubmissionCreateSerializer,
        responses={201: SubmissionSerializer}
    )
    def post(self, request, team_id):
        team = get_object_or_404(Team.objects.select_related('event'), pk=team_id)
        if not is_team_member(team, request.user):
            raise exceptions.PermissionDenied("You must be a member of this team to create a submission.")

        # Deadline guard
        if timezone.now() > team.event.submission_deadline:
            raise exceptions.ValidationError({'detail': "The submission deadline for this event has passed. New submissions are closed."})

        # Check existing submission
        existing = team.submissions.first()
        if existing:
            return Response(SubmissionSerializer(existing).data, status=status.HTTP_200_OK)

        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submission = Submission(
            team=team,
            event=team.event,
            status=Submission.Status.DRAFT,
            **serializer.validated_data
        )
        try:
            submission.save(actor=request.user)
        except ValidationError as e:
            raise exceptions.ValidationError(e.message_dict if hasattr(e, 'message_dict') else str(e))

        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


class SubmissionDetailUpdateAPIView(APIView):
    """
    GET /api/submissions/{pk}/
    Retrieve submission details.

    PUT/PATCH /api/submissions/{pk}/
    Edit submission details and optionally submit.
    Strictly enforces submission deadline before permitting any changes.
    """
    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="Retrieve project submission details",
        responses={200: SubmissionSerializer}
    )
    def get(self, request, pk):
        submission = get_object_or_404(
            Submission.objects.select_related('team', 'event', 'track').prefetch_related('gallery_images'),
            pk=pk
        )
        return Response(SubmissionSerializer(submission).data)

    def _update_submission(self, request, pk, partial=False):
        submission = get_object_or_404(
            Submission.objects.select_related('team', 'event', 'track').prefetch_related('gallery_images'),
            pk=pk
        )

        if not is_team_member(submission.team, request.user):
            raise exceptions.PermissionDenied("You must be a member of this team to edit this submission.")

        # DEADLINE GUARD
        if timezone.now() > submission.event.submission_deadline:
            AuditLogEntry.log(
                'submission.deadline_blocked_edit_attempt',
                submission,
                actor=request.user,
                metadata={'event_id': submission.event.pk, 'deadline': submission.event.submission_deadline.isoformat()}
            )
            raise exceptions.PermissionDenied("The submission deadline for this event has passed. No further edits are permitted.")

        serializer = SubmissionUpdateSerializer(submission, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data.pop('action', 'save_draft')

        for attr, value in serializer.validated_data.items():
            setattr(submission, attr, value)

        if action == 'submit_final':
            submission.status = Submission.Status.SUBMITTED

        try:
            submission.save(actor=request.user)
        except ValidationError as e:
            raise exceptions.ValidationError(e.message_dict if hasattr(e, 'message_dict') else str(e))

        return Response(SubmissionSerializer(submission).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update project submission details",
        request=SubmissionUpdateSerializer,
        responses={200: SubmissionSerializer}
    )
    def put(self, request, pk):
        return self._update_submission(request, pk, partial=False)

    @extend_schema(
        summary="Partially update project submission details",
        request=SubmissionUpdateSerializer,
        responses={200: SubmissionSerializer}
    )
    def patch(self, request, pk):
        return self._update_submission(request, pk, partial=True)


class SubmissionImageUploadAPIView(APIView):
    """
    POST /api/submissions/{pk}/gallery/
    Upload a gallery screenshot for this submission. Enforces deadline.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload a screenshot to submission gallery",
        request=SubmissionImageUploadSerializer,
        responses={201: SubmissionImageSerializer}
    )
    def post(self, request, pk):
        submission = get_object_or_404(Submission.objects.select_related('event', 'team'), pk=pk)
        if not is_team_member(submission.team, request.user):
            raise exceptions.PermissionDenied("Unauthorized.")

        if timezone.now() > submission.event.submission_deadline:
            AuditLogEntry.log('submission.deadline_blocked_edit_attempt', submission, actor=request.user)
            raise exceptions.PermissionDenied("Deadline passed. Image uploads are closed.")

        serializer = SubmissionImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        img = serializer.save(submission=submission)
        return Response(SubmissionImageSerializer(img).data, status=status.HTTP_201_CREATED)


class SubmissionImageDeleteAPIView(APIView):
    """
    DELETE /api/submissions/{pk}/gallery/{image_id}/
    Delete a gallery screenshot. Enforces deadline.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete a screenshot from submission gallery",
        responses={204: None}
    )
    def delete(self, request, pk, image_id):
        submission = get_object_or_404(Submission.objects.select_related('event', 'team'), pk=pk)
        if not is_team_member(submission.team, request.user):
            raise exceptions.PermissionDenied("Unauthorized.")

        if timezone.now() > submission.event.submission_deadline:
            AuditLogEntry.log('submission.deadline_blocked_edit_attempt', submission, actor=request.user)
            raise exceptions.PermissionDenied("Deadline passed. Image modifications are closed.")

        img = get_object_or_404(SubmissionImage, pk=image_id, submission=submission)
        img.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
