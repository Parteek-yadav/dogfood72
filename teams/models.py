"""
Teams data models for Dogfood 2026.
"""

import secrets
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Team(models.Model):
    """
    Hacker team participating within a specific Event.
    """
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='teams'
    )
    name = models.CharField(max_length=255, help_text="Team name")
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_teams',
        help_text="User who originally formed the team"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['event', 'name'], name='unique_event_team_name')
        ]
        indexes = [
            models.Index(fields=['event', 'name']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.event.name})"

    def is_member(self, user):
        """Check if a given user is a member of this team."""
        if not user or not user.is_authenticated:
            return False
        return self.memberships.filter(user=user).exists()

    def get_leader(self):
        """Return the primary team leader user, if assigned."""
        leader_membership = self.memberships.filter(role=TeamMembership.Role.LEADER).select_related('user').first()
        return leader_membership.user if leader_membership else self.created_by


class TeamMembership(models.Model):
    """
    Associates a User with a Team, specifying their role (leader or member).
    """
    class Role(models.TextChoices):
        LEADER = 'leader', 'Team Leader'
        MEMBER = 'member', 'Team Member'

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='team_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Team Membership"
        verbose_name_plural = "Team Memberships"
        ordering = ['joined_at']
        constraints = [
            models.UniqueConstraint(fields=['team', 'user'], name='unique_team_user_membership')
        ]
        indexes = [
            models.Index(fields=['team', 'role']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} ({self.team.name})"


def generate_invite_token():
    return secrets.token_urlsafe(32)


class Invite(models.Model):
    """
    Invitation token allowing a user to join a specific Team.
    Supports email gating, expiration timestamps, and single-use invalidation.
    """
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='invites'
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_invite_token,
        help_text="Cryptographically secure URL-safe invite token"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='sent_team_invites'
    )
    email = models.EmailField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional target email address for email-gated invites"
    )
    expires_at = models.DateTimeField(help_text="Timestamp when the invite becomes invalid")
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this invite was accepted and used"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Team Invite"
        verbose_name_plural = "Team Invites"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['team', 'expires_at']),
        ]

    def __str__(self):
        status = "Used" if self.used_at else ("Expired" if self.is_expired() else "Active")
        target = f" to {self.email}" if self.email else ""
        return f"Invite for {self.team.name}{target} [{status}]"

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def is_valid(self):
        """Returns True if invite has not expired and has not been used."""
        return self.used_at is None and not self.is_expired()
