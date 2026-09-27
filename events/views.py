"""
Event views for Dogfood 2026.
Includes Event CRUD and organizer CustomQuestion management.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from core.permissions import event_organizer_required, is_event_organizer, is_event_participant
from core.models import AuditLogEntry
from .models import Event, EventRole, Track, Prize, CustomQuestion
from .forms import EventForm, TrackForm, PrizeForm, CustomQuestionForm


def event_list(request):
    """Public event directory: lists published events, plus draft events for organizers."""
    now = timezone.now()
    if request.user.is_authenticated:
        # Show published events OR events organized by this user
        events = Event.objects.filter(
            models_Q_filter := (
                Event.objects.filter(is_published=True) |
                Event.objects.filter(organizer=request.user) |
                Event.objects.filter(roles__user=request.user, roles__role=EventRole.Role.ORGANIZER)
            ).query
        ).distinct()
    else:
        events = Event.objects.filter(is_published=True)

    return render(request, 'events/event_list.html', {
        'events': events,
        'now': now
    })


def event_detail(request, slug):
    """Event homepage showing description, dates, tracks, prizes, and team actions."""
    event = get_object_or_404(Event, slug=slug)
    is_organizer = is_event_organizer(event, request.user)

    if not event.is_published and not is_organizer:
        raise PermissionDenied("This event has not been published yet.")

    user_team = None
    if request.user.is_authenticated:
        user_team = event.teams.filter(memberships__user=request.user).first()

    return render(request, 'events/event_detail.html', {
        'event': event,
        'is_organizer': is_organizer,
        'user_team': user_team,
        'tracks': event.tracks.all(),
        'prizes': event.prizes.select_related('track').all(),
        'questions': event.custom_questions.all(),
    })


@login_required
def event_create(request):
    """Create a new Hackathon event. Automatically assigns organizer role."""
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()

            # Assign organizer role
            EventRole.objects.get_or_create(
                event=event,
                user=request.user,
                role=EventRole.Role.ORGANIZER
            )

            AuditLogEntry.log('event.created', event, actor=request.user)
            messages.success(request, f"Event '{event.name}' successfully created!")
            return redirect('events:event_manage', slug=event.slug)
    else:
        form = EventForm()

    return render(request, 'events/event_form.html', {'form': form, 'title': 'Create New Event'})


@event_organizer_required
def event_edit(request, slug):
    """Edit core event timeline and details."""
    event = get_object_or_404(Event, slug=slug)
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save()
            AuditLogEntry.log('event.edited', event, actor=request.user)
            messages.success(request, f"Event details for '{event.name}' updated.")
            return redirect('events:event_manage', slug=event.slug)
    else:
        form = EventForm(instance=event)

    return render(request, 'events/event_form.html', {
        'form': form,
        'event': event,
        'title': f"Edit Event: {event.name}"
    })


@event_organizer_required
def event_manage(request, slug):
    """Organizer dashboard: manage details, custom questions, tracks, and prizes."""
    event = get_object_or_404(Event, slug=slug)
    question_form = CustomQuestionForm()
    track_form = TrackForm()
    prize_form = PrizeForm(event=event)

    return render(request, 'events/event_manage.html', {
        'event': event,
        'questions': event.custom_questions.all(),
        'tracks': event.tracks.all(),
        'prizes': event.prizes.all(),
        'question_form': question_form,
        'track_form': track_form,
        'prize_form': prize_form,
    })


@event_organizer_required
@require_POST
def event_question_add(request, slug):
    """Add a new organizer-defined custom question."""
    event = get_object_or_404(Event, slug=slug)
    form = CustomQuestionForm(request.POST)
    if form.is_valid():
        question = form.save(commit=False)
        question.event = event
        question.choices = form.cleaned_data['parsed_choices']
        question.save()
        AuditLogEntry.log('event.question_added', question, actor=request.user, metadata={'label': question.label})
        messages.success(request, f"Custom question '{question.label}' added.")
    else:
        messages.error(request, "Failed to add question. Please check form errors.")
    return redirect('events:event_manage', slug=event.slug)


@event_organizer_required
@require_POST
def event_question_delete(request, slug, question_id):
    """Delete an organizer-defined custom question."""
    event = get_object_or_404(Event, slug=slug)
    question = get_object_or_404(CustomQuestion, pk=question_id, event=event)
    label = question.label
    question.delete()
    AuditLogEntry.log('event.question_deleted', event, actor=request.user, metadata={'question_id': question_id, 'label': label})
    messages.success(request, f"Custom question '{label}' removed.")
    return redirect('events:event_manage', slug=event.slug)


@event_organizer_required
@require_POST
def event_question_reorder(request, slug):
    """Reorder custom questions."""
    event = get_object_or_404(Event, slug=slug)
    for key, value in request.POST.items():
        if key.startswith('order_'):
            try:
                q_id = int(key.replace('order_', ''))
                order_val = int(value)
                CustomQuestion.objects.filter(pk=q_id, event=event).update(order=order_val)
            except ValueError:
                continue
    messages.success(request, "Question order updated.")
    return redirect('events:event_manage', slug=event.slug)


@event_organizer_required
@require_POST
def event_track_add(request, slug):
    """Add a track to the event."""
    event = get_object_or_404(Event, slug=slug)
    form = TrackForm(request.POST)
    if form.is_valid():
        track = form.save(commit=False)
        track.event = event
        track.save()
        messages.success(request, f"Track '{track.name}' added.")
    return redirect('events:event_manage', slug=event.slug)


@event_organizer_required
@require_POST
def event_track_delete(request, slug, track_id):
    """Delete a track from the event."""
    event = get_object_or_404(Event, slug=slug)
    track = get_object_or_404(Track, pk=track_id, event=event)
    track.delete()
    messages.success(request, f"Track removed.")
    return redirect('events:event_manage', slug=event.slug)


@event_organizer_required
@require_POST
def event_prize_add(request, slug):
    """Add a prize to the event."""
    event = get_object_or_404(Event, slug=slug)
    form = PrizeForm(request.POST, event=event)
    if form.is_valid():
        prize = form.save(commit=False)
        prize.event = event
        prize.save()
        messages.success(request, f"Prize '{prize.name}' added.")
    return redirect('events:event_manage', slug=event.slug)


@event_organizer_required
@require_POST
def event_prize_delete(request, slug, prize_id):
    """Delete a prize from the event."""
    event = get_object_or_404(Event, slug=slug)
    prize = get_object_or_404(Prize, pk=prize_id, event=event)
    prize.delete()
    messages.success(request, f"Prize removed.")
    return redirect('events:event_manage', slug=event.slug)
