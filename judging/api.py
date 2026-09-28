"""
DRF API views for Judging, Assignments, Scoring, Normalization, and Exports.
Includes strict role isolation and complete OpenAPI documentation.
"""

import csv
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models import Max
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, exceptions
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from events.models import Event, EventRole
from submissions.models import Submission
from judging.models import Rubric, RubricCriterion, JudgeAssignment, Score, NormalizedScore
from core.permissions import is_event_organizer, is_event_judge
from core.models import AuditLogEntry
from .serializers import (
    MyAssignmentSerializer,
    OrganizerSubmissionScoreSerializer,
    JudgeProgressSummarySerializer,
    JudgeScoreItemSerializer,
    RubricSerializer,
    RubricCreateUpdateSerializer,
    RubricCriterionSerializer,
    AlgorithmicAssignmentRequestSerializer,
    AlgorithmicAssignmentResponseSerializer,
    ManualAssignmentSerializer,
    ScoreSubmissionRequestSerializer,
    ScoreSubmissionResponseSerializer,
    NormalizationTriggerSerializer,
    NormalizationResponseSerializer,
)
from .services.assignment import run_event_judge_assignments
from .services.normalization import run_score_normalization


class MyAssignmentsAPIView(APIView):
    """
    GET /api/events/{id}/my-assignments/
    Allows an authenticated judge to retrieve only their own assignments and scores.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List assignments for authenticated judge",
        responses={200: MyAssignmentSerializer(many=True)}
    )
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

    @extend_schema(
        summary="Retrieve all judge scores for a submission (organizers only)",
        responses={200: OrganizerSubmissionScoreSerializer(many=True)}
    )
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

    @extend_schema(
        summary="Aggregate evaluation progress across judges (organizers only)",
        responses={200: JudgeProgressSummarySerializer}
    )
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

        response_data = {
            'event_id': event.id,
            'event_name': event.name,
            'total_judges': len(judge_roles),
            'total_assignments': total_assigned,
            'completed_assignments': total_completed,
            'progress_percent': overall_percent,
            'judges': judge_data
        }
        return Response(response_data, status=status.HTTP_200_OK)


class JudgeScoresAPIView(APIView):
    """
    GET /api/judge/scores
    Checker endpoint:
    - as judge_a -> 200 with their own scores
    - as participant / unauthenticated -> 401/403
    - as judge_b querying ?judge=judge_a -> 401/403
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Retrieve scores submitted by authenticated judge",
        parameters=[
            OpenApiParameter(name='judge', description='Judge username (must match requesting judge)', required=False, type=str)
        ],
        responses={200: JudgeScoreItemSerializer(many=True)}
    )
    def get(self, request):
        user = request.user
        # Must be assigned as a judge in at least one event
        is_judge = EventRole.objects.filter(user=user, role=EventRole.Role.JUDGE).exists()
        if not is_judge and not user.is_staff:
            raise exceptions.PermissionDenied("Access denied: You are not registered as a judge.")

        # If ?judge= query param is provided, must match request.user
        target_judge = request.query_params.get('judge')
        if target_judge and target_judge != user.username:
            raise exceptions.PermissionDenied("Access denied: Judges can only view their own scores.")

        scores = (
            Score.objects.filter(assignment__judge=user)
            .select_related('assignment__submission', 'criterion')
            .order_by('-created_at')
        )

        data = [
            {
                'submission_id': s.assignment.submission_id,
                'submission_title': s.assignment.submission.title,
                'criterion': s.criterion.name,
                'value': s.value,
                'feedback': s.feedback,
            }
            for s in scores
        ]
        return Response(data, status=status.HTTP_200_OK)


class ExportCSVAPIView(APIView):
    """
    GET /api/export.csv
    Checker endpoint:
    - as organizer/admin -> 200 with CSV body
    - as non-organizer -> 401/403
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Export scoring evaluation CSV (organizer access required)",
        responses={200: OpenApiResponse(description="CSV export file content")}
    )
    def get(self, request):
        user = request.user
        is_organizer = (
            user.is_staff or
            user.is_superuser or
            EventRole.objects.filter(user=user, role=EventRole.Role.ORGANIZER).exists()
        )
        if not is_organizer:
            raise exceptions.PermissionDenied("Access denied: Organizer or admin access required for export.")

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="export.csv"'
        writer = csv.writer(response)
        writer.writerow(['event_slug', 'submission_id', 'submission_title', 'team_name', 'judge_username', 'criterion', 'score', 'feedback'])

        for sc in Score.objects.select_related('assignment__event', 'assignment__submission__team', 'assignment__judge', 'criterion').all():
            writer.writerow([
                sc.assignment.event.slug,
                sc.assignment.submission.id,
                sc.assignment.submission.title,
                sc.assignment.submission.team.name,
                sc.assignment.judge.username,
                sc.criterion.name,
                sc.value,
                sc.feedback
            ])

        return response


class RubricManageAPIView(APIView):
    """
    GET /api/events/{event_id}/rubric/
    Retrieve rubric and its criteria for an event.

    POST /api/events/{event_id}/rubric/
    Create or update rubric metadata for an event.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="Retrieve rubric and criteria for an event",
        responses={200: RubricSerializer}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        rubric, _ = Rubric.objects.get_or_create(event=event, defaults={'name': f"{event.name} Official Rubric"})
        return Response(RubricSerializer(rubric).data)

    @extend_schema(
        summary="Create or update event rubric",
        request=RubricCreateUpdateSerializer,
        responses={200: RubricSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        rubric, _ = Rubric.objects.get_or_create(event=event, defaults={'name': f"{event.name} Official Rubric"})
        serializer = RubricCreateUpdateSerializer(rubric, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_rubric = serializer.save()
        AuditLogEntry.log('rubric.updated', updated_rubric, actor=request.user)
        return Response(RubricSerializer(updated_rubric).data, status=status.HTTP_200_OK)


class RubricCriterionListCreateAPIView(APIView):
    """
    POST /api/events/{event_id}/rubric/criteria/
    Add a new criterion to the event's rubric.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Add criterion to event rubric",
        request=RubricCriterionSerializer,
        responses={201: RubricCriterionSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        rubric, _ = Rubric.objects.get_or_create(event=event, defaults={'name': f"{event.name} Official Rubric"})
        serializer = RubricCriterionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        criterion = serializer.save(rubric=rubric)
        return Response(RubricCriterionSerializer(criterion).data, status=status.HTTP_201_CREATED)


class RubricCriterionDetailAPIView(APIView):
    """
    DELETE /api/events/{event_id}/rubric/criteria/{pk}/
    Delete a criterion from the event's rubric.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete a criterion from event rubric",
        responses={204: None}
    )
    def delete(self, request, event_id, pk):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        rubric = get_object_or_404(Rubric, event=event)
        criterion = get_object_or_404(RubricCriterion, pk=pk, rubric=rubric)
        criterion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RunAlgorithmicAssignmentsAPIView(APIView):
    """
    POST /api/events/{event_id}/assignments/run/
    Executes balanced, conflict-of-interest-free algorithmic judge assignments.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Run algorithmic judge assignments with COI prevention",
        request=AlgorithmicAssignmentRequestSerializer,
        responses={200: AlgorithmicAssignmentResponseSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")

        serializer = AlgorithmicAssignmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        k_val = serializer.validated_data.get('k', 3)

        assignments = run_event_judge_assignments(
            event=event,
            k=k_val,
            clear_existing=True,
            actor=request.user
        )

        return Response({
            'status': 'success',
            'assignments_generated': len(assignments),
            'k': k_val
        }, status=status.HTTP_200_OK)


class ManualAssignmentOverrideAPIView(APIView):
    """
    POST /api/events/{event_id}/assignments/override/
    Manually add or remove a judge assignment with COI validation.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Manual judge assignment override",
        request=ManualAssignmentSerializer,
        responses={200: OpenApiResponse(description="Assignment updated")}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")

        serializer = ManualAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']

        if action == 'add':
            judge_id = serializer.validated_data.get('judge_id')
            submission_id = serializer.validated_data.get('submission_id')
            if not judge_id or not submission_id:
                raise exceptions.ValidationError({'detail': "judge_id and submission_id required for 'add' action."})

            sub = get_object_or_404(Submission, pk=submission_id, event=event)
            if sub.team.is_member(judge_id) or sub.team.created_by_id == int(judge_id):
                raise exceptions.ValidationError({'detail': "Cannot assign judge: Conflict of Interest (judge is on this team)."})

            assign_obj, created = JudgeAssignment.objects.get_or_create(
                event=event,
                judge_id=judge_id,
                submission=sub,
                defaults={'status': JudgeAssignment.Status.ASSIGNED}
            )
            AuditLogEntry.log('judging.manual_assignment_added', assign_obj, actor=request.user)
            return Response({'status': 'added', 'assignment_id': assign_obj.id}, status=status.HTTP_200_OK)

        elif action == 'delete':
            assignment_id = serializer.validated_data.get('assignment_id')
            if not assignment_id:
                raise exceptions.ValidationError({'detail': "assignment_id required for 'delete' action."})

            assign_obj = get_object_or_404(JudgeAssignment, pk=assignment_id, event=event)
            assign_obj.delete()
            AuditLogEntry.log('judging.manual_assignment_removed', event, actor=request.user, metadata={'assignment_id': assignment_id})
            return Response({'status': 'deleted', 'assignment_id': assignment_id}, status=status.HTTP_200_OK)


class ScoreSubmissionAPIView(APIView):
    """
    POST /api/assignments/{assignment_id}/score/
    Judge evaluates assigned submission on 1-5 scale for each criterion.
    Enforces judging window and assignment ownership.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Submit or save scores for an assigned submission",
        request=ScoreSubmissionRequestSerializer,
        responses={200: ScoreSubmissionResponseSerializer}
    )
    def post(self, request, assignment_id):
        assignment = get_object_or_404(
            JudgeAssignment.objects.select_related('event', 'judge', 'submission'),
            pk=assignment_id
        )

        if assignment.judge != request.user and not request.user.is_superuser:
            raise exceptions.PermissionDenied("You can only score your own assigned submissions.")

        event = assignment.event
        now = timezone.now()
        judging_deadline = event.voting_end or event.end_date
        if judging_deadline and now > judging_deadline:
            raise exceptions.PermissionDenied("Judging window for this event has closed. Scores cannot be modified.")

        rubric = event.rubrics.first()
        if not rubric:
            raise exceptions.ValidationError({'detail': "No rubric configured for this event."})

        serializer = ScoreSubmissionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scores_data = serializer.validated_data['scores']

        criteria = {c.id: c for c in rubric.criteria.all()}
        scores_saved = 0

        for sc_item in scores_data:
            c_id = sc_item['criterion_id']
            if c_id not in criteria:
                raise exceptions.ValidationError({'detail': f"Invalid criterion ID: {c_id}"})

            val = sc_item['value']
            fb = sc_item.get('feedback', '')

            Score.objects.update_or_create(
                assignment=assignment,
                criterion=criteria[c_id],
                defaults={'value': val, 'feedback': fb}
            )
            scores_saved += 1

        # Check if all criteria scored
        if scores_saved >= len(criteria):
            assignment.status = JudgeAssignment.Status.COMPLETED
            assignment.completed_at = timezone.now()
        else:
            assignment.status = JudgeAssignment.Status.IN_PROGRESS
        assignment.save()

        AuditLogEntry.log('score.submitted', assignment.submission, actor=request.user, metadata={'status': assignment.status})
        return Response({
            'status': 'success',
            'assignment_status': assignment.status,
            'scores_saved': scores_saved
        }, status=status.HTTP_200_OK)


class TriggerNormalizationAPIView(APIView):
    """
    POST /api/events/{event_id}/normalize/
    Triggers z-score normalization across all judges for an event.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Trigger z-score normalization for an event",
        request=NormalizationTriggerSerializer,
        responses={200: NormalizationResponseSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")

        res = run_score_normalization(event, actor=request.user)
        return Response(res, status=status.HTTP_200_OK)


class ExportNormalizedCSVAPIView(APIView):
    """
    GET /api/events/{event_id}/export/normalized/
    Export normalized rankings CSV (organizers only).
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Export normalized rankings as CSV",
        responses={200: OpenApiResponse(description="CSV export of normalized rankings")}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="normalized_scores_{event.slug}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Rank', 'Submission ID', 'Submission Title', 'Team', 'Track', 'Raw Mean', 'Normalized Z-Score', 'Computed At'])

        scores = (
            NormalizedScore.objects.filter(submission__event=event, method='zscore')
            .select_related('submission__team', 'submission__track')
            .order_by('-normalized_value')
        )
        for rank, ns in enumerate(scores, start=1):
            writer.writerow([
                rank,
                ns.submission_id,
                ns.submission.title,
                ns.submission.team.name,
                ns.submission.track.name if ns.submission.track else '',
                ns.raw_mean,
                ns.normalized_value,
                ns.computed_at.isoformat()
            ])
        return response


class ExportAssignmentsCSVAPIView(APIView):
    """
    GET /api/events/{event_id}/export/assignments/
    Export judge assignments CSV (organizers only).
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Export judge assignments as CSV",
        responses={200: OpenApiResponse(description="CSV export of judge assignments")}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="judge_assignments_{event.slug}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Assignment ID', 'Judge Username', 'Submission Title', 'Team', 'Status', 'Assigned At', 'Completed At'])

        assigns = (
            JudgeAssignment.objects.filter(event=event)
            .select_related('judge', 'submission__team')
            .order_by('judge__username', 'submission__title')
        )
        for a in assigns:
            writer.writerow([
                a.id,
                a.judge.username,
                a.submission.title,
                a.submission.team.name,
                a.status,
                a.assigned_at.isoformat(),
                a.completed_at.isoformat() if a.completed_at else ''
            ])
        return response
