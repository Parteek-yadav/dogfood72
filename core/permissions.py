"""
Role enforcement and permission helpers for Dogfood 2026.

Provides reusable permission checks, Django View mixins, decorators, and DRF permission
classes for server-side authorization. Never rely on template-level conditional hiding alone.
"""

from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from rest_framework import permissions

from events.models import Event, EventRole
from teams.models import Team, TeamMembership


# ==============================================================================
# Functional Permission Checkers
# ==============================================================================

def is_event_organizer(event, user):
    """
    Returns True if user is the primary organizer, has an 'organizer' EventRole,
    or is a platform superuser.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if event.organizer_id == user.id:
        return True
    return event.roles.filter(user=user, role=EventRole.Role.ORGANIZER).exists()


def is_event_judge(event, user):
    """
    Returns True if user is assigned as a judge for this event or is a platform superuser.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return event.roles.filter(user=user, role=EventRole.Role.JUDGE).exists()


def is_event_participant(event, user):
    """
    Returns True if user is an event participant (via EventRole or team membership).
    """
    if not user or not user.is_authenticated:
        return False
    if event.roles.filter(user=user, role=EventRole.Role.PARTICIPANT).exists():
        return True
    return TeamMembership.objects.filter(team__event=event, user=user).exists()


def is_team_member(team, user):
    """
    Returns True if user is a member or leader of the specified team, or is a superuser.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return team.memberships.filter(user=user).exists()


def is_team_leader(team, user):
    """
    Returns True if user is the creator or leader of the team, or is a superuser.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or team.created_by_id == user.id:
        return True
    return team.memberships.filter(user=user, role=TeamMembership.Role.LEADER).exists()


# ==============================================================================
# Django View Mixins
# ==============================================================================

class EventOrganizerRequiredMixin:
    """
    CBV mixin enforcing that request.user must be an organizer of the event.
    Looks for self.get_event() or self.kwargs['slug'] / self.kwargs['event_id'].
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        event = self.get_event()
        if not is_event_organizer(event, request.user):
            raise PermissionDenied("You do not have organizer permissions for this event.")
        return super().dispatch(request, *args, **kwargs)

    def get_event(self):
        if hasattr(self, 'event') and self.event is not None:
            return self.event
        if 'slug' in self.kwargs:
            return get_object_or_404(Event, slug=self.kwargs['slug'])
        if 'event_id' in self.kwargs:
            return get_object_or_404(Event, pk=self.kwargs['event_id'])
        raise NotImplementedError("EventOrganizerRequiredMixin requires 'slug' or 'event_id' in URL kwargs or get_event().")


class EventJudgeRequiredMixin:
    """
    CBV mixin enforcing that request.user must be an authorized judge of the event.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        event = self.get_event()
        if not is_event_judge(event, request.user):
            raise PermissionDenied("You do not have judge permissions for this event.")
        return super().dispatch(request, *args, **kwargs)

    def get_event(self):
        if hasattr(self, 'event') and self.event is not None:
            return self.event
        if 'slug' in self.kwargs:
            return get_object_or_404(Event, slug=self.kwargs['slug'])
        if 'event_id' in self.kwargs:
            return get_object_or_404(Event, pk=self.kwargs['event_id'])
        raise NotImplementedError("EventJudgeRequiredMixin requires 'slug' or 'event_id' in URL kwargs or get_event().")


class TeamMemberRequiredMixin:
    """
    CBV mixin enforcing that request.user must be an authorized member of the team.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        team = self.get_team()
        if not is_team_member(team, request.user):
            raise PermissionDenied("You are not a member of this team.")
        return super().dispatch(request, *args, **kwargs)

    def get_team(self):
        if hasattr(self, 'team') and self.team is not None:
            return self.team
        if 'team_id' in self.kwargs:
            return get_object_or_404(Team, pk=self.kwargs['team_id'])
        if 'pk' in self.kwargs:
            return get_object_or_404(Team, pk=self.kwargs['pk'])
        raise NotImplementedError("TeamMemberRequiredMixin requires 'team_id' or 'pk' in URL kwargs.")


# ==============================================================================
# Django View Decorators
# ==============================================================================

def event_organizer_required(view_func):
    """
    Decorator for FBVs taking (request, slug=..., ...) or (request, event_id=..., ...).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        event_slug = kwargs.get('slug')
        event_id = kwargs.get('event_id')
        if event_slug:
            event = get_object_or_404(Event, slug=event_slug)
        elif event_id:
            event = get_object_or_404(Event, pk=event_id)
        else:
            raise ValueError("event_organizer_required decorator expects 'slug' or 'event_id' in kwargs.")
        if not is_event_organizer(event, request.user):
            raise PermissionDenied("You do not have organizer permissions for this event.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def event_judge_required(view_func):
    """
    Decorator for FBVs taking (request, slug=..., ...) or (request, event_id=..., ...).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        event_slug = kwargs.get('slug')
        event_id = kwargs.get('event_id')
        if event_slug:
            event = get_object_or_404(Event, slug=event_slug)
        elif event_id:
            event = get_object_or_404(Event, pk=event_id)
        else:
            raise ValueError("event_judge_required decorator expects 'slug' or 'event_id' in kwargs.")
        if not is_event_judge(event, request.user):
            raise PermissionDenied("You do not have judge permissions for this event.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# ==============================================================================
# Django REST Framework Permission Classes
# ==============================================================================

class IsEventOrganizer(permissions.BasePermission):
    """
    DRF permission: allows access only to organizers of the target Event.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        event = obj if isinstance(obj, Event) else getattr(obj, 'event', None)
        if not event:
            return False
        return is_event_organizer(event, request.user)


class IsEventJudge(permissions.BasePermission):
    """
    DRF permission: allows access only to assigned judges of the target Event.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        event = obj if isinstance(obj, Event) else getattr(obj, 'event', None)
        if not event:
            return False
        return is_event_judge(event, request.user)


class IsTeamMember(permissions.BasePermission):
    """
    DRF permission: allows access only to members of the target Team (or team-linked obj).
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        team = obj if isinstance(obj, Team) else getattr(obj, 'team', None)
        if not team:
            return False
        return is_team_member(team, request.user)
