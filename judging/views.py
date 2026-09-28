"""
Judging views for Dogfood 2026.
Includes Rubric builder, Judge assignment manager, Judge scoring interface,
organizer progress dashboard, normalization runner, and CSV data exports.
"""

import csv
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.contrib.auth.models import User

from core.permissions import event_organizer_required, is_event_organizer, is_event_judge
from core.models import AuditLogEntry
from events.models import Event, EventRole
from submissions.models import Submission
from .models import Rubric, RubricCriterion, JudgeAssignment, Score, NormalizedScore
from .forms import RubricForm, RubricCriterionFormSet, JudgeAssignmentForm, ScoreInputForm
from .services.assignment import run_event_judge_assignments
from .services.normalization import run_score_normalization


# ==============================================================================
# 1. Rubric Builder (Organizer)
# ==============================================================================

@event_organizer_required
def rubric_manage(request, event_id):
    """
    Organizer creates or edits an evaluation Rubric and its criteria with weights.
    Validates that criteria weights sum to 100.00%.
    """
    event = get_object_or_404(Event, pk=event_id)
    rubric, _ = Rubric.objects.get_or_create(event=event, defaults={'name': f"{event.name} Official Rubric"})

    if request.method == 'POST':
        form = RubricForm(request.POST, instance=rubric)
        formset = RubricCriterionFormSet(request.POST, instance=rubric)

        if form.is_valid() and formset.is_valid():
            instances = formset.save(commit=False)
            for inst in instances:
                inst.rubric = rubric
                inst.save()
            for obj in formset.deleted_objects:
                obj.delete()
            form.save()

            total_weight = rubric.total_weight()
            if total_weight != Decimal('100.00'):
                messages.warning(
                    request,
                    f"Rubric saved, but criteria weights currently sum to {total_weight}% (target is 100.00%)."
                )
            else:
                messages.success(request, "Rubric and criteria successfully updated!")

            AuditLogEntry.log('rubric.updated', rubric, actor=request.user, metadata={'total_weight': str(total_weight)})
            return redirect('judging:rubric_manage', event_id=event.pk)
    else:
        form = RubricForm(instance=rubric)
        formset = RubricCriterionFormSet(instance=rubric)

    return render(request, 'judging/rubric_manage.html', {
        'event': event,
        'rubric': rubric,
        'form': form,
        'formset': formset,
        'total_weight': rubric.total_weight(),
    })


# ==============================================================================
# 2. Judge Assignment & Algorithmic Balancer (Organizer)
# ==============================================================================

@event_organizer_required
def assignment_manage(request, event_id):
    """
    Organizer interface to run algorithmic judge assignments and perform manual overrides.
    """
    event = get_object_or_404(Event, pk=event_id)
    assignments = (
        JudgeAssignment.objects.filter(event=event)
        .select_related('judge', 'submission__team')
        .order_by('submission__title', 'judge__username')
    )

    judges = EventRole.objects.filter(event=event, role=EventRole.Role.JUDGE).select_related('user')
    submissions = Submission.objects.filter(event=event, status=Submission.Status.SUBMITTED)

    manual_form = JudgeAssignmentForm()
    manual_form.fields['judge'].queryset = User.objects.filter(id__in=judges.values_list('user_id', flat=True))
    manual_form.fields['submission'].queryset = submissions

    return render(request, 'judging/assignment_manage.html', {
        'event': event,
        'assignments': assignments,
        'judges': judges,
        'submissions': submissions,
        'manual_form': manual_form,
    })


@event_organizer_required
@require_POST
def run_algorithmic_assignments(request, event_id):
    """Executes the balanced, COI-free algorithmic judge assignment."""
    event = get_object_or_404(Event, pk=event_id)
    k_val = int(request.POST.get('k', 3))

    assignments = run_event_judge_assignments(event=event, k=k_val, clear_existing=True, actor=request.user)
    messages.success(request, f"Generated {len(assignments)} judge assignments (K={k_val}) with zero conflicts of interest.")
    return redirect('judging:assignment_manage', event_id=event.pk)


@event_organizer_required
@require_POST
def manual_assignment_override(request, event_id):
    """Manual assignment override by organizer."""
    event = get_object_or_404(Event, pk=event_id)
    action = request.POST.get('action')

    if action == 'add':
        judge_id = request.POST.get('judge')
        submission_id = request.POST.get('submission')
        if judge_id and submission_id:
            sub = get_object_or_404(Submission, pk=submission_id, event=event)
            # Check COI
            if sub.team.is_member(judge_id) or sub.team.created_by_id == int(judge_id):
                messages.error(request, "Cannot assign judge: Conflict of Interest (judge is on this team).")
            else:
                obj, created = JudgeAssignment.objects.get_or_create(
                    event=event,
                    judge_id=judge_id,
                    submission=sub,
                    defaults={'status': JudgeAssignment.Status.ASSIGNED}
                )
                AuditLogEntry.log('judging.manual_assignment_added', obj, actor=request.user)
                messages.success(request, "Assignment added successfully.")
    elif action == 'delete':
        assignment_id = request.POST.get('assignment_id')
        if assignment_id:
            assign = get_object_or_404(JudgeAssignment, pk=assignment_id, event=event)
            assign.delete()
            AuditLogEntry.log('judging.manual_assignment_removed', event, actor=request.user, metadata={'assignment_id': assignment_id})
            messages.success(request, "Assignment removed.")

    return redirect('judging:assignment_manage', event_id=event.pk)


# ==============================================================================
# 3. Judge Scoring Portal
# ==============================================================================

@login_required
def my_assignments(request):
    """Displays assignments allocated to the logged-in judge across active events."""
    assignments = (
        JudgeAssignment.objects.filter(judge=request.user)
        .select_related('event', 'submission__team', 'submission__track')
        .order_by('-assigned_at')
    )
    return render(request, 'judging/my_assignments.html', {
        'assignments': assignments,
    })


@login_required
def score_submission(request, assignment_id):
    """
    Judge scoring interface for an assigned submission.
    Evaluates against all rubric criteria, permits partial saves, and enforces judging window.
    """
    assignment = get_object_or_404(
        JudgeAssignment.objects.select_related('event', 'judge', 'submission__team', 'submission__track'),
        pk=assignment_id
    )

    if assignment.judge != request.user and not request.user.is_superuser:
        raise PermissionDenied("You can only score your own assigned submissions.")

    event = assignment.event
    rubric = event.rubrics.first()
    if not rubric:
        messages.error(request, "No evaluation rubric has been configured for this event yet.")
        return redirect('judging:my_assignments')

    criteria = list(rubric.criteria.all())
    if not criteria:
        messages.error(request, "The rubric has no criteria configured.")
        return redirect('judging:my_assignments')

    # Enforce judging window (closes at voting_end, representing the evaluation window conclusion, or end_date)
    now = timezone.now()
    judging_deadline = event.voting_end or event.end_date
    is_window_closed = (judging_deadline and now > judging_deadline)

    # Fetch existing scores
    existing_scores = {s.criterion_id: {'value': s.value, 'feedback': s.feedback} for s in assignment.scores.all()}

    if request.method == 'POST':
        if is_window_closed:
            raise PermissionDenied("Judging window for this event has closed. Scores cannot be modified.")

        form = ScoreInputForm(request.POST, criteria=criteria, initial_scores=existing_scores)
        if form.is_valid():
            all_scored = True
            for crit in criteria:
                val = form.cleaned_data.get(f"criterion_{crit.id}")
                fb = form.cleaned_data.get(f"feedback_{crit.id}", "")

                if val is not None:
                    Score.objects.update_or_create(
                        assignment=assignment,
                        criterion=crit,
                        defaults={'value': val, 'feedback': fb}
                    )
                else:
                    all_scored = False

            if all_scored:
                assignment.status = JudgeAssignment.Status.COMPLETED
                assignment.completed_at = timezone.now()
                messages.success(request, f"Evaluation completed for '{assignment.submission.title}'!")
            else:
                assignment.status = JudgeAssignment.Status.IN_PROGRESS
                messages.info(request, "Partial scoring draft saved.")

            assignment.save()
            AuditLogEntry.log('score.submitted', assignment.submission, actor=request.user, metadata={'status': assignment.status})
            return redirect('judging:my_assignments')
    else:
        form = ScoreInputForm(criteria=criteria, initial_scores=existing_scores)

    return render(request, 'judging/score_submission.html', {
        'assignment': assignment,
        'submission': assignment.submission,
        'event': event,
        'rubric': rubric,
        'criteria': criteria,
        'form': form,
        'is_window_closed': is_window_closed,
        'gallery_images': assignment.submission.gallery_images.all(),
    })


# ==============================================================================
# 4. Judge Progress Dashboard & Normalization (Organizer UI)
# ==============================================================================

@event_organizer_required
def judge_progress_dashboard(request, event_id):
    """
    Organizer live dashboard tracking judge progress and displaying normalized rankings.
    """
    event = get_object_or_404(Event, pk=event_id)
    judge_roles = (
        EventRole.objects.filter(event=event, role=EventRole.Role.JUDGE)
        .select_related('user')
        .order_by('user__username')
    )

    judges_summary = []
    total_assigned = 0
    total_completed = 0

    for jr in judge_roles:
        u = jr.user
        assigns = JudgeAssignment.objects.filter(event=event, judge=u)
        assigned_cnt = assigns.count()
        completed_cnt = assigns.filter(status=JudgeAssignment.Status.COMPLETED).count()
        in_prog_cnt = assigns.filter(status=JudgeAssignment.Status.IN_PROGRESS).count()
        last_score_time = Score.objects.filter(assignment__in=assigns).aggregate(latest=Max('updated_at'))['latest']

        total_assigned += assigned_cnt
        total_completed += completed_cnt

        pct = round((completed_cnt / assigned_cnt) * 100, 1) if assigned_cnt > 0 else 0.0

        judges_summary.append({
            'user': u,
            'assigned': assigned_cnt,
            'completed': completed_cnt,
            'in_progress': in_prog_cnt,
            'percent': pct,
            'last_activity': last_score_time,
        })

    overall_percent = round((total_completed / total_assigned) * 100, 1) if total_assigned > 0 else 0.0

    # Fetch latest normalized scores if available
    normalized_scores = (
        NormalizedScore.objects.filter(submission__event=event, method='zscore')
        .select_related('submission__team', 'submission__track')
        .order_by('-normalized_value')
    )

    return render(request, 'judging/judge_progress.html', {
        'event': event,
        'judges_summary': judges_summary,
        'total_assigned': total_assigned,
        'total_completed': total_completed,
        'overall_percent': overall_percent,
        'normalized_scores': normalized_scores,
    })


@event_organizer_required
@require_POST
def trigger_normalization_view(request, event_id):
    """Triggers score normalization from the organizer dashboard."""
    event = get_object_or_404(Event, pk=event_id)
    res = run_score_normalization(event, actor=request.user)

    if res.get('status') == 'success':
        messages.success(request, f"Z-score normalization complete across {res['submission_count']} submissions and {res['judge_count']} judges.")
    else:
        messages.warning(request, res.get('message', "No scores available to normalize."))

    return redirect('judging:judge_progress_dashboard', event_id=event.pk)


# ==============================================================================
# 5. CSV Data Exports
# ==============================================================================

@event_organizer_required
def export_raw_scores_csv(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="raw_scores_{event.slug}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Submission ID', 'Submission Title', 'Team', 'Judge Username', 'Criterion', 'Weight', 'Score (1-5)', 'Feedback', 'Updated At'])

    scores = (
        Score.objects.filter(assignment__event=event)
        .select_related('assignment__submission__team', 'assignment__judge', 'criterion')
        .order_by('assignment__submission__title', 'assignment__judge__username')
    )
    for s in scores:
        writer.writerow([
            s.assignment.submission_id,
            s.assignment.submission.title,
            s.assignment.submission.team.name,
            s.assignment.judge.username,
            s.criterion.name,
            s.criterion.weight,
            s.value,
            s.feedback,
            s.updated_at.isoformat()
        ])
    return response


@event_organizer_required
def export_normalized_scores_csv(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
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


@event_organizer_required
def export_judge_assignments_csv(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
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
