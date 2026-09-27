"""
DRF API views for Judging & Role Isolation.

Strict Security Rules:
- GET /api/events/{id}/my-assignments/
    Judge sees ONLY their own assigned submissions and ONLY their own scores.
- GET /api/submissions/{id}/scores/
    Must return 403 Forbidden for any judge or non-organizer trying to view
    scores on a submission. Returns 200 with full visibility ONLY for event organizers/admin.
- GET /api/events/{id}/judge-progress/
    Returns 403 Forbidden for non-organizers. Returns 200 aggregate stats for organizers/admin.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, exceptions
from django.shortcuts import get_object_or_404
from django.db.models import Max

from events.models import Event, EventRole
from submissions.models import Submission
from judging.models import JudgeAssignment, Score
from core.permissions import is_event_organizer, is_event_judge
from .serializers import MyAssignmentSerializer, OrganizerSubmissionScoreSerializer


class MyAssignmentsAPIView(APIView):
    """
    GET /api/events/{id}/my-assignments/
    Allows an authenticated judge to retrieve only their own assignments and scores.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)

        # Retrieve assignments strictly assigned to request.user
        assignments = (
            JudgeAssignment.objects.filter(event=event, judge=request.user)
            .select_related('submission__team', 'submission__track')
            .prefetch_related('scores__criterion')
            .order_by('-assigned_at')
        )

        serializer = MyAssignmentSerializer(assignments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SubmissionScoresAPIView(APIView):
    """
    GET /api/submissions/{id}/scores/

    STRICT ISOLATION REQUIREMENT:
    - Must return 403 Forbidden for a judge trying to view scores on this submission.
    - Must return 200 with full visibility ONLY for event organizers and platform administrators.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, submission_id):
        submission = get_object_or_404(Submission.objects.select_related('event'), pk=submission_id)

        # Check organizer permission
        if not is_event_organizer(submission.event, request.user):
            raise exceptions.PermissionDenied(
                "Access denied: You do not have organizer permissions to view multi-judge evaluation scores for this submission."
            )

        # Organizers see all judge evaluations for this submission
        assignments = (
            JudgeAssignment.objects.filter(submission=submission)
            .select_related('judge')
            .prefetch_related('scores__criterion')
            .order_by('judge__username')
        )

        serializer = OrganizerSubmissionScoreSerializer(assignments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class JudgeProgressAPIView(APIView):
    """
    GET /api/events/{id}/judge-progress/

    STRICT ISOLATION REQUIREMENT:
    - Must return 403 Forbidden for non-organizers.
    - Returns aggregate evaluation progress for organizers/admins.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)

        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied(
                "Access denied: Only event organizers can view aggregate judging progress."
            )

        # Collect event judges
        judge_roles = (
            EventRole.objects.filter(event=event, role=EventRole.Role.JUDGE)
            .select_related('user')
            .order_by('user__username')
        )

        judge_data = []
        total_assigned = 0
        total_completed = 0

        for jr in judge_roles:
            user = jr.user
            assignments = JudgeAssignment.objects.filter(event=event, judge=user)
            assigned_count = assignments.count()
            completed_count = assignments.filter(status=JudgeAssignment.Status.COMPLETED).count()
            in_progress_count = assignments.filter(status=JudgeAssignment.Status.IN_PROGRESS).count()
            unstarted_count = assignments.filter(status=JudgeAssignment.Status.ASSIGNED).count()

            # Find last activity (latest score timestamp or assignment completion)
            last_score_time = Score.objects.filter(assignment__in=assignments).aggregate(latest=Max('updated_at'))['latest']

            total_assigned += assigned_count
            total_completed += completed_count

            judge_data.append({
                'judge_id': user.id,
                'username': user.username,
                'email': user.email,
                'assigned_count': assigned_count,
                'completed_count': completed_count,
                'in_progress_count': in_progress_count,
                'unstarted_count': unstarted_count,
                'last_activity': last_score_time.isoformat() if last_score_time else None
            })

        overall_percent = (
            round((total_completed / total_assigned) * 100, 1)
            if total_assigned > 0 else 0.0
        )

        return Response({
            'event_id': event.id,
            'event_name': event.name,
            'total_judges': len(judge_roles),
            'total_assignments': total_assigned,
            'completed_assignments': total_completed,
            'progress_percent': overall_percent,
            'judges': judge_data
        }, status=status.HTTP_200_OK)
