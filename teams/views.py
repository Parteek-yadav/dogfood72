"""
Team views for Dogfood 2026.
Handles team formation, expiring/signed invite links, and member joining.
"""

from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.urls import reverse

from core.permissions import is_team_member, is_team_leader
from core.models import AuditLogEntry
from events.models import Event, EventRole
from .models import Team, TeamMembership, Invite
from .forms import TeamForm, InviteForm


@login_required
def team_create(request, event_slug):
    """
    Form a new team for an event.
    Enforces that a user can only be on one team per event.
    """
    event = get_object_or_404(Event, slug=event_slug)

    # Check if user is already on a team for this event
    existing_membership = TeamMembership.objects.filter(team__event=event, user=request.user).first()
    if existing_membership:
        messages.error(
            request,
            f"You are already a member of team '{existing_membership.team.name}' in this event. "
            "A participant cannot belong to multiple teams in the same event."
        )
        return redirect('teams:team_detail', pk=existing_membership.team.pk)

    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save(commit=False)
            team.event = event
            team.created_by = request.user
            team.save()

            # Assign creator as Leader
            TeamMembership.objects.create(
                team=team,
                user=request.user,
                role=TeamMembership.Role.LEADER
            )

            # Assign Event participant role
            EventRole.objects.get_or_create(
                event=event,
                user=request.user,
                role=EventRole.Role.PARTICIPANT
            )

            AuditLogEntry.log('team.created', team, actor=request.user)
            messages.success(request, f"Team '{team.name}' created! You can now invite teammates.")
            return redirect('teams:team_detail', pk=team.pk)
    else:
        form = TeamForm()

    return render(request, 'teams/team_form.html', {
        'form': form,
        'event': event,
        'title': f"Create Team for {event.name}"
    })


@login_required
def team_detail(request, pk):
    """View team roster, pending invites, and submission status."""
    team = get_object_or_404(Team.objects.select_related('event', 'created_by'), pk=pk)
    user_is_member = is_team_member(team, request.user)
    user_is_leader = is_team_leader(team, request.user)

    invite_form = InviteForm() if user_is_member else None
    active_invites = team.invites.filter(used_at__isnull=True, expires_at__gt=timezone.now()) if user_is_member else []

    # Get team submission if any
    submission = getattr(team, 'submissions', None)
    submission_obj = team.submissions.first() if hasattr(team, 'submissions') else None

    return render(request, 'teams/team_detail.html', {
        'team': team,
        'memberships': team.memberships.select_related('user').all(),
        'user_is_member': user_is_member,
        'user_is_leader': user_is_leader,
        'invite_form': invite_form,
        'active_invites': active_invites,
        'submission': submission_obj,
    })


@login_required
@require_POST
def team_invite_create(request, pk):
    """Generate a shareable, expiring invite token."""
    team = get_object_or_404(Team, pk=pk)
    if not is_team_member(team, request.user):
        messages.error(request, "Only team members can generate invite links.")
        return redirect('teams:team_detail', pk=team.pk)

    form = InviteForm(request.POST)
    if form.is_valid():
        days = form.cleaned_data['expires_in_days']
        email = form.cleaned_data.get('email') or None

        invite = Invite.objects.create(
            team=team,
            created_by=request.user,
            email=email,
            expires_at=timezone.now() + timedelta(days=days)
        )
        AuditLogEntry.log('team.invite_created', team, actor=request.user, metadata={'invite_id': invite.pk, 'email': email})
        messages.success(request, "Invitation link generated!")
    else:
        messages.error(request, "Failed to create invite. Check form inputs.")

    return redirect('teams:team_detail', pk=team.pk)


@login_required
def team_join(request, token):
    """
    Accept an invitation to join a team via secure token.
    Validates token expiration, reuse, and single-team-per-event constraint.
    """
    invite = get_object_or_404(Invite.objects.select_related('team__event'), token=token)
    team = invite.team
    event = team.event

    # 1. Check if token already used
    if invite.used_at is not None:
        messages.error(request, "This invitation link has already been used.")
        return render(request, 'teams/join_error.html', {'error': "This invitation link has already been used.", 'team': team})

    # 2. Check if token expired
    if invite.is_expired():
        messages.error(request, "This invitation link has expired.")
        return render(request, 'teams/join_error.html', {'error': "This invitation link has expired.", 'team': team})

    # 3. Check if invite is restricted to another email
    if invite.email and request.user.email.lower() != invite.email.lower():
        error_msg = f"This invitation is restricted to {invite.email}. You are logged in as {request.user.email}."
        messages.error(request, error_msg)
        return render(request, 'teams/join_error.html', {'error': error_msg, 'team': team})

    # 4. Check if user is already in this team
    if team.is_member(request.user):
        messages.info(request, f"You are already a member of team '{team.name}'.")
        return redirect('teams:team_detail', pk=team.pk)

    # 5. Check if user is already on a different team for this event
    existing_membership = TeamMembership.objects.filter(team__event=event, user=request.user).first()
    if existing_membership:
        error_msg = (
            f"You are already a member of team '{existing_membership.team.name}' in this event. "
            "A participant cannot belong to multiple teams in the same event."
        )
        messages.error(request, error_msg)
        return render(request, 'teams/join_error.html', {'error': error_msg, 'team': team})

    # If POST (confirmation) or GET (show preview and confirmation button)
    if request.method == 'POST':
        # Add to team
        TeamMembership.objects.create(
            team=team,
            user=request.user,
            role=TeamMembership.Role.MEMBER
        )

        # Mark invite as used
        invite.used_at = timezone.now()
        invite.save()

        # Assign event participant role
        EventRole.objects.get_or_create(
            event=event,
            user=request.user,
            role=EventRole.Role.PARTICIPANT
        )

        AuditLogEntry.log('team.joined', team, actor=request.user, metadata={'invite_id': invite.pk})
        messages.success(request, f"Welcome to team '{team.name}'!")
        return redirect('teams:team_detail', pk=team.pk)

    return render(request, 'teams/team_join_confirm.html', {
        'team': team,
        'event': event,
        'invite': invite,
    })
