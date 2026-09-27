"""
Events data models for Dogfood 2026.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.text import slugify


class Event(models.Model):
    """
    Hackathon event entity. Holds schedule timelines, publication status,
    and event creator reference.
    """
    name = models.CharField(max_length=255, help_text="Event title")
    slug = models.SlugField(max_length=255, unique=True, db_index=True, help_text="Unique URL slug")
    description = models.TextField(help_text="Full markdown/text description of the event")
    start_date = models.DateTimeField(help_text="Event start timestamp")
    end_date = models.DateTimeField(help_text="Event conclusion timestamp")
    submission_deadline = models.DateTimeField(help_text="Deadline for submission submissions and edits")
    voting_start = models.DateTimeField(help_text="Start of community/judge voting period")
    voting_end = models.DateTimeField(help_text="End of community/judge voting period")
    is_published = models.BooleanField(default=False, db_index=True, help_text="Whether event is visible to public")
    organizer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='organized_events',
        help_text="Primary event creator / lead organizer"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Event"
        verbose_name_plural = "Events"
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_published', 'submission_deadline']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({'end_date': "End date must be strictly after start date."})
        if self.voting_start and self.voting_end and self.voting_start >= self.voting_end:
            raise ValidationError({'voting_end': "Voting end must be strictly after voting start."})

    def is_user_organizer(self, user):
        """Check if a given user is the creator or assigned an organizer role for this event."""
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or self.organizer_id == user.id:
            return True
        return self.roles.filter(user=user, role=EventRole.Role.ORGANIZER).exists()

    def is_user_judge(self, user):
        """Check if a user is assigned as a judge for this event."""
        if not user or not user.is_authenticated:
            return False
        return self.roles.filter(user=user, role=EventRole.Role.JUDGE).exists()

    def is_user_participant(self, user):
        """Check if a user is an active participant in this event."""
        if not user or not user.is_authenticated:
            return False
        return self.roles.filter(user=user, role=EventRole.Role.PARTICIPANT).exists()


class EventRole(models.Model):
    """
    Per-event role assignments: Participant, Judge, or Organizer.
    Decoupled from global User model to permit multi-role users across different events.
    """
    class Role(models.TextChoices):
        ORGANIZER = 'organizer', 'Organizer'
        JUDGE = 'judge', 'Judge'
        PARTICIPANT = 'participant', 'Participant'

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='roles'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='event_roles'
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        db_index=True
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Event Role"
        verbose_name_plural = "Event Roles"
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user', 'role'],
                name='unique_event_user_role'
            )
        ]
        indexes = [
            models.Index(fields=['event', 'role']),
            models.Index(fields=['user', 'role']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} ({self.event.name})"


class Track(models.Model):
    """
    Optional challenge tracks or themes within an event (e.g., 'Best AI/ML', 'Best UI/UX').
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='tracks'
    )
    name = models.CharField(max_length=255, help_text="Track name")
    description = models.TextField(blank=True, help_text="Description and criteria for this track")

    class Meta:
        verbose_name = "Track"
        verbose_name_plural = "Tracks"
        ordering = ['event', 'name']
        constraints = [
            models.UniqueConstraint(fields=['event', 'name'], name='unique_event_track_name')
        ]

    def __str__(self):
        return f"{self.event.name} - {self.name}"


class Prize(models.Model):
    """
    Prize offerings for an event, optionally associated with a specific track.
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='prizes'
    )
    track = models.ForeignKey(
        Track,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prizes',
        help_text="Optional track restriction for this prize"
    )
    name = models.CharField(max_length=255, help_text="Prize title (e.g. '1st Place Overall')")
    amount = models.CharField(max_length=255, blank=True, help_text="Cash value or prize description (e.g. '$5,000')")
    description = models.TextField(blank=True, help_text="Details on eligibility and prize perks")
    rank = models.PositiveIntegerField(default=1, help_text="Prize ranking order (e.g. 1 for 1st, 2 for 2nd)")

    class Meta:
        verbose_name = "Prize"
        verbose_name_plural = "Prizes"
        ordering = ['rank', 'name']
        indexes = [
            models.Index(fields=['event', 'rank']),
        ]

    def __str__(self):
        return f"{self.name} ({self.event.name})"


class CustomQuestion(models.Model):
    """
    Organizer-defined custom questions for submission forms.
    Defines field types, requirements, and allowed choices for select inputs.
    """
    class FieldType(models.TextChoices):
        TEXT = 'text', 'Single-line Text'
        TEXTAREA = 'textarea', 'Multi-line Text (Textarea)'
        URL = 'url', 'URL'
        SELECT = 'select', 'Select Dropdown'
        CHECKBOX = 'checkbox', 'Checkbox (Boolean)'

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='custom_questions'
    )
    label = models.CharField(max_length=255, help_text="The prompt or label displayed to the participant")
    field_type = models.CharField(
        max_length=20,
        choices=FieldType.choices,
        default=FieldType.TEXT,
        help_text="Input control type"
    )
    required = models.BooleanField(
        default=False,
        help_text="Whether this question must be answered upon final submission"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order sequence within the submission form"
    )
    choices = models.JSONField(
        default=list,
        blank=True,
        help_text="List of choices for 'select' field type, e.g. [\"Option A\", \"Option B\"]"
    )

    class Meta:
        verbose_name = "Custom Question"
        verbose_name_plural = "Custom Questions"
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['event', 'order']),
        ]

    def __str__(self):
        req_tag = " *" if self.required else ""
        return f"[{self.event.name}] {self.label}{req_tag} ({self.get_field_type_display()})"

    def clean(self):
        super().clean()
        if self.field_type == self.FieldType.SELECT:
            if not isinstance(self.choices, list) or len(self.choices) == 0:
                raise ValidationError({
                    'choices': "For 'select' questions, choices must be a non-empty JSON list of options."
                })
