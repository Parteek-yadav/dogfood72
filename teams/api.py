"""
DRF API views for Teams, Invites, and Team Joining.
"""

from datetime import timedelta
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.models import AuditLogEntry
from core.permissions import is_team_member, is_team_leader
from events.models import Event, EventRole
from .models import Team, TeamMembership, Invite
from .serializers import (
    TeamDetailSerializer,
    TeamCreateSerializer,
    InviteSerializer,
    InviteCreateSerializer,
    TeamMembershipSerializer,
)


class EventTeamListCreateAPIView(APIView):
    """
    GET /api/events/{event_id}/teams/
    List teams formed in this event.

    POST /api/events/{event_id}/teams/
    Form a new team for this event. Enforces single-team-per-event constraint.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="List teams for an event",
        responses={200: TeamDetailSerializer(many=True)}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        teams = event.teams.select_related('event', 'created_by').prefetch_related('memberships__user').all()
        return Response(TeamDetailSerializer(teams, many=True).data)

    @extend_schema(
        summary="Create a new team for an event",
        request=TeamCreateSerializer,
        responses={201: TeamDetailSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)

        # Check single-team constraint
        existing = TeamMembership.objects.filter(team__event=event, user=request.user).first()
        if existing:
            raise exceptions.ValidationError({
                'detail': f"You are already a member of team '{existing.team.name}' in this event."
            })

        serializer = TeamCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = serializer.save(event=event, created_by=request.user)

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
        return Response(TeamDetailSerializer(team).data, status=status.HTTP_201_CREATED)


class TeamDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/teams/{pk}/
    Retrieve team details and roster.
    """
    queryset = Team.objects.select_related('event', 'created_by').prefetch_related('memberships__user').all()
    serializer_class = TeamDetailSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Retrieve team details and roster",
        responses={200: TeamDetailSerializer}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class TeamInviteCreateAPIView(APIView):
    """
    POST /api/teams/{pk}/invites/
    Generate a shareable, expiring invite token. Only team members can create invites.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Create an invitation token for a team",
        request=InviteCreateSerializer,
        responses={201: InviteSerializer}
    )
    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        if not is_team_member(team, request.user):
            raise exceptions.PermissionDenied("Only team members can generate invite links.")

        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        days = serializer.validated_data.get('expires_in_days', 7)
        email = serializer.validated_data.get('email') or None

        invite = Invite.objects.create(
            team=team,
            created_by=request.user,
            email=email,
            expires_at=timezone.now() + timedelta(days=days)
        )
        AuditLogEntry.log('team.invite_created', team, actor=request.user, metadata={'invite_id': invite.pk, 'email': email})
        return Response(InviteSerializer(invite).data, status=status.HTTP_201_CREATED)


class TeamJoinAPIView(APIView):
    """
    POST /api/invites/{token}/join/
    Accept an invitation to join a team via token.
    Validates expiration, reuse, and single-team-per-event constraint.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Join a team using an invite token",
        request=None,
        responses={200: TeamDetailSerializer}
    )
    def post(self, request, token):
        invite = get_object_or_404(Invite.objects.select_related('team__event'), token=token)
        team = invite.team
        event = team.event

        # 1. Check if token already used
        if invite.used_at is not None:
            raise exceptions.ValidationError({'detail': "This invitation link has already been used."})

        # 2. Check if token expired
        if invite.is_expired():
            raise exceptions.ValidationError({'detail': "This invitation link has expired."})

        # 3. Check email restriction
        if invite.email and request.user.email.lower() != invite.email.lower():
            raise exceptions.PermissionDenied(f"This invitation is restricted to {invite.email}.")

        # 4. Check if already in team
        if team.is_member(request.user):
            return Response(TeamDetailSerializer(team).data, status=status.HTTP_200_OK)

        # 5. Check if in different team for this event
        existing = TeamMembership.objects.filter(team__event=event, user=request.user).first()
        if existing:
            raise exceptions.ValidationError({
                'detail': f"You are already a member of team '{existing.team.name}' in this event."
            })

        # Add member
        TeamMembership.objects.create(
            team=team,
            user=request.user,
            role=TeamMembership.Role.MEMBER
        )

        # Mark invite used
        invite.used_at = timezone.now()
        invite.save()

        # Assign event participant role
        EventRole.objects.get_or_create(
            event=event,
            user=request.user,
            role=EventRole.Role.PARTICIPANT
        )

        AuditLogEntry.log('team.joined', team, actor=request.user, metadata={'invite_id': invite.pk})
        return Response(TeamDetailSerializer(team).data, status=status.HTTP_200_OK)


class TeamMemberRemoveAPIView(APIView):
    """
    DELETE /api/teams/{pk}/members/{user_id}/
    Remove a member from the team. Only the team leader or the user themselves may execute this.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Remove a member from the team",
        responses={204: None}
    )
    def delete(self, request, pk, user_id):
        team = get_object_or_404(Team, pk=pk)
        membership = get_object_or_404(TeamMembership, team=team, user_id=user_id)

        is_leader = is_team_leader(team, request.user)
        is_self = (request.user.id == int(user_id))

        if not (is_leader or is_self):
            raise exceptions.PermissionDenied("You do not have permission to remove this member.")

        membership.delete()
        AuditLogEntry.log('team.member_removed', team, actor=request.user, metadata={'removed_user_id': user_id})
        return Response(status=status.HTTP_204_NO_CONTENT)
