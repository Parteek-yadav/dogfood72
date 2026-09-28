"""
Submission views for Dogfood 2026.
Handles draft creation, edits with deadline guards, gallery uploads, and the public gallery.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q

from core.permissions import is_team_member
from core.models import AuditLogEntry
from events.models import Event
from teams.models import Team
from .models import Submission, SubmissionImage
from .forms import SubmissionForm, SubmissionImageForm


@login_required
def submission_create(request, team_id):
    """Create initial draft project submission for a team."""
    team = get_object_or_404(Team.objects.select_related('event'), pk=team_id)
    if not is_team_member(team, request.user):
        raise PermissionDenied("You must be a member of this team to create a submission.")

    # Check deadline
    if timezone.now() > team.event.submission_deadline:
        messages.error(request, "The submission deadline for this event has passed. New submissions are closed.")
        return redirect('teams:team_detail', pk=team.pk)

    # If team already has a submission, redirect to edit
    existing = team.submissions.first()
    if existing:
        return redirect('submissions:submission_edit', pk=existing.pk)

    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES, event=team.event)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.team = team
            submission.event = team.event
            submission.tech_tags = form.cleaned_data['parsed_tech_tags']
            submission.custom_answers = form.cleaned_data['parsed_custom_answers']
            submission.status = Submission.Status.DRAFT

            try:
                submission.save(actor=request.user)
                messages.success(request, f"Draft submission '{submission.title}' created! You can continue editing until the deadline.")
                return redirect('submissions:submission_edit', pk=submission.pk)
            except ValidationError as e:
                form.add_error(None, e)
    else:
        form = SubmissionForm(event=team.event)

    return render(request, 'submissions/submission_form.html', {
        'form': form,
        'team': team,
        'event': team.event,
        'title': f"New Submission for {team.name}"
    })


@login_required
def submission_edit(request, pk):
    """
    Edit project submission, answer custom questions, and optionally submit.
    Strictly enforces submission deadline in the view layer before handling POST edits.
    """
    submission = get_object_or_404(
        Submission.objects.select_related('team', 'event', 'track').prefetch_related('gallery_images'),
        pk=pk
    )

    if not is_team_member(submission.team, request.user):
        raise PermissionDenied("You must be a member of this team to edit this submission.")

    # DEADLINE GUARD: reject any edit attempt after submission deadline
    if timezone.now() > submission.event.submission_deadline:
        AuditLogEntry.log(
            'submission.deadline_blocked_edit_attempt',
            submission,
            actor=request.user,
            metadata={'event_id': submission.event.pk, 'deadline': submission.event.submission_deadline.isoformat()}
        )
        raise PermissionDenied("The submission deadline for this event has passed. No further edits are permitted.")

    image_form = SubmissionImageForm()

    if request.method == 'POST':
        action = request.POST.get('action', 'save_draft')
        form = SubmissionForm(request.POST, request.FILES, instance=submission, event=submission.event)

        if form.is_valid():
            sub = form.save(commit=False)
            sub.tech_tags = form.cleaned_data['parsed_tech_tags']
            sub.custom_answers = form.cleaned_data['parsed_custom_answers']

            if action == 'submit_final':
                sub.status = Submission.Status.SUBMITTED

            try:
                sub.save(actor=request.user)
                if sub.status == Submission.Status.SUBMITTED:
                    messages.success(request, f"Project '{sub.title}' successfully submitted for judging!")
                    return redirect('submissions:submission_detail', pk=sub.pk)
                else:
                    messages.success(request, "Draft saved successfully.")
                    return redirect('submissions:submission_edit', pk=sub.pk)
            except ValidationError as e:
                if hasattr(e, 'message_dict'):
                    for field, errs in e.message_dict.items():
                        if field == 'custom_answers':
                            for q_err in errs:
                                form.add_error(None, f"Custom Question Error: {q_err}")
                        else:
                            form.add_error(field if field in form.fields else None, errs)
                else:
                    form.add_error(None, str(e))
    else:
        form = SubmissionForm(instance=submission, event=submission.event)

    return render(request, 'submissions/submission_form.html', {
        'form': form,
        'image_form': image_form,
        'submission': submission,
        'team': submission.team,
        'event': submission.event,
        'title': f"Edit Submission: {submission.title}",
        'gallery_images': submission.gallery_images.all(),
    })


@login_required
@require_POST
def submission_image_upload(request, pk):
    """Upload a gallery screenshot for this submission."""
    submission = get_object_or_404(Submission.objects.select_related('event', 'team'), pk=pk)
    if not is_team_member(submission.team, request.user):
        raise PermissionDenied("Unauthorized.")

    if timezone.now() > submission.event.submission_deadline:
        AuditLogEntry.log('submission.deadline_blocked_edit_attempt', submission, actor=request.user)
        raise PermissionDenied("Deadline passed. Image uploads are closed.")

    form = SubmissionImageForm(request.POST, request.FILES)
    if form.is_valid():
        img = form.save(commit=False)
        img.submission = submission
        img.save()
        messages.success(request, "Gallery image uploaded.")
    else:
        messages.error(request, "Failed to upload image. Please provide a valid image file.")

    return redirect('submissions:submission_edit', pk=submission.pk)


@login_required
@require_POST
def submission_image_delete(request, pk, image_id):
    """Delete a gallery screenshot."""
    submission = get_object_or_404(Submission.objects.select_related('event', 'team'), pk=pk)
    if not is_team_member(submission.team, request.user):
        raise PermissionDenied("Unauthorized.")

    if timezone.now() > submission.event.submission_deadline:
        AuditLogEntry.log('submission.deadline_blocked_edit_attempt', submission, actor=request.user)
        raise PermissionDenied("Deadline passed. Image modifications are closed.")

    img = get_object_or_404(SubmissionImage, pk=image_id, submission=submission)
    img.delete()
    messages.success(request, "Gallery image removed.")
    return redirect('submissions:submission_edit', pk=submission.pk)


def submission_detail(request, pk):
    """Public and participant presentation view for a submission."""
    submission = get_object_or_404(
        Submission.objects.select_related('team', 'event', 'track').prefetch_related('gallery_images'),
        pk=pk
    )

    # Format custom question answers with question labels
    questions_map = {str(q.id): q for q in submission.event.custom_questions.all()}
    answered_questions = []
    for q_id, val in submission.custom_answers.items():
        question = questions_map.get(str(q_id))
        if question:
            answered_questions.append({
                'label': question.label,
                'value': val,
                'field_type': question.field_type
            })

    is_team_member_user = is_team_member(submission.team, request.user)

    return render(request, 'submissions/submission_detail.html', {
        'submission': submission,
        'event': submission.event,
        'gallery_images': submission.gallery_images.all(),
        'answered_questions': answered_questions,
        'is_team_member': is_team_member_user,
    })


def public_gallery(request, slug):
    """
    Public gallery displaying all submitted projects for a published event.
    Supports text search across titles and tech tags, plus filtering by Track.
    """
    event = get_object_or_404(Event, slug=slug)

    # Only show if published (or if organizer)
    from core.permissions import is_event_organizer
    if not event.is_published and not is_event_organizer(event, request.user):
        raise PermissionDenied("Event is not published.")

    submissions_qs = (
        Submission.objects.filter(event=event, status=Submission.Status.SUBMITTED)
        .select_related('team', 'track')
        .prefetch_related('gallery_images')
    )

    # Search filter (title, tagline, tech tags)
    search_query = request.GET.get('q', '').strip()
    if search_query:
        submissions_qs = submissions_qs.filter(
            Q(title__icontains=search_query) |
            Q(tagline__icontains=search_query) |
            Q(tech_tags__icontains=search_query)
        )

    # Track filter
    track_id = request.GET.get('track', '').strip()
    if track_id:
        submissions_qs = submissions_qs.filter(track_id=track_id)

    tracks = event.tracks.all()

    return render(request, 'submissions/public_gallery.html', {
        'event': event,
        'submissions': submissions_qs,
        'tracks': tracks,
        'selected_track': track_id,
        'search_query': search_query,
    })


def projects_list(request):
    """
    Public listing of projects for route GET /projects.
    Returns 200 with project titles from fixture submissions.
    """
    event = Event.objects.filter(is_published=True).first() or Event.objects.first()
    submissions_qs = (
        Submission.objects.filter(status=Submission.Status.SUBMITTED)
        .select_related('event', 'team', 'track')
        .prefetch_related('gallery_images')
    )
    return render(request, 'submissions/public_gallery.html', {
        'event': event,
        'submissions': submissions_qs,
        'tracks': event.tracks.all() if event else [],
        'selected_track': '',
        'search_query': '',
    })


def projects_new(request):
    """
    Submission creation for route POST /projects/new.
    Rejects with 403 Forbidden because event submissions are closed.
    """
    from django.http import HttpResponseForbidden
    return HttpResponseForbidden("The submission deadline for this event has passed. Submissions are closed.")

