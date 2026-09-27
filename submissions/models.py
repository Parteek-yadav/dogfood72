"""
Submissions data models for Dogfood 2026.

VERSIONING DECISION NOTE:
-------------------------
We implement an explicit `SubmissionVersion` model alongside `Submission.updated_at`.
While `updated_at` provides basic recency, hackathons require an immutable audit trail
of draft iterations, final pre-deadline updates, and post-deadline modifications to
resolve disputes and protect academic/intellectual integrity.
Each edit persists a snapshot row in `SubmissionVersion`.
"""

from urllib.parse import urlparse
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone


class Submission(models.Model):
    """
    Primary hackathon project submission entity.
    Belongs to a Team within an Event, optionally tagged to a Track.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'

    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='submissions',
        help_text="Team authoring this project"
    )
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    track = models.ForeignKey(
        'events.Track',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions',
        help_text="Track entered by this submission"
    )
    title = models.CharField(max_length=255, help_text="Project title")
    tagline = models.CharField(max_length=255, blank=True, help_text="One-line elevator pitch")
    description = models.TextField(help_text="Full project description and markdown writeup")
    thumbnail = models.ImageField(
        upload_to='submissions/thumbnails/',
        blank=True,
        null=True,
        help_text="Cover/card thumbnail image for the submission"
    )
    repo_url = models.URLField(blank=True, help_text="Source code repository (e.g. GitHub/GitLab)")
    live_url = models.URLField(blank=True, help_text="Live running deployment URL")
    demo_video_url = models.URLField(blank=True, help_text="Demo video URL (e.g. YouTube, Vimeo, Loom)")
    tech_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of technologies / stacks used (e.g. [\"Python\", \"Django\", \"PostgreSQL\"])"
    )
    custom_answers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Organizer-defined custom question answers keyed by str(CustomQuestion.id)"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp when project was officially submitted"
    )

    class Meta:
        verbose_name = "Submission"
        verbose_name_plural = "Submissions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event', 'status']),
            models.Index(fields=['team', 'event']),
            models.Index(fields=['created_at']),
            models.Index(fields=['submitted_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.team.name} - {self.event.name})"

    def clean(self):
        super().clean()
        # Ensure team belongs to the selected event
        if self.team_id and self.event_id and self.team.event_id != self.event_id:
            raise ValidationError({'team': "The selected team must belong to the specified event."})

        # Ensure track belongs to the selected event if specified
        if self.track_id and self.event_id and self.track.event_id != self.event_id:
            raise ValidationError({'track': "The selected track must belong to the specified event."})

        # Validate custom_answers against the Event's CustomQuestion definitions
        if self.event_id:
            self.validate_custom_answers()

    def validate_custom_answers(self):
        """
        Validate custom_answers dictionary against the event's configured CustomQuestion set.
        - Enforces allowed keys (must be valid question IDs for this event).
        - Enforces required questions when status is 'submitted'.
        - Validates choice restrictions for 'select' question types.
        - Validates boolean values for 'checkbox' types.
        - Validates URL syntax for 'url' types.
        """
        if not isinstance(self.custom_answers, dict):
            raise ValidationError({'custom_answers': "custom_answers must be a JSON object / dictionary."})

        questions = {str(q.id): q for q in self.event.custom_questions.all()}
        errors = {}

        # Check for disallowed / orphaned question IDs
        for q_id_key in self.custom_answers.keys():
            if str(q_id_key) not in questions:
                errors[q_id_key] = f"Question ID '{q_id_key}' does not exist on event '{self.event.name}'."

        # Validate each defined question for this event
        for q_id_str, question in questions.items():
            val = self.custom_answers.get(q_id_str)

            # Check required fields
            is_empty = val is None or val == "" or (isinstance(val, list) and len(val) == 0)
            if question.required and self.status == self.Status.SUBMITTED and is_empty:
                errors[q_id_str] = f"Question '{question.label}' is required."
                continue

            # Validate type-specific constraints if answer is provided
            if not is_empty:
                if question.field_type == 'select':
                    if question.choices and val not in question.choices:
                        errors[q_id_str] = f"'{val}' is not a valid choice for '{question.label}'. Allowed: {question.choices}"
                elif question.field_type == 'checkbox':
                    if not isinstance(val, bool):
                        errors[q_id_str] = f"Answer to '{question.label}' must be a boolean (true/false)."
                elif question.field_type == 'url':
                    parsed = urlparse(str(val))
                    if not (parsed.scheme in ('http', 'https') and parsed.netloc):
                        errors[q_id_str] = f"Answer to '{question.label}' must be a valid HTTP/HTTPS URL."

        if errors:
            raise ValidationError({'custom_answers': errors})

    def save(self, *args, **kwargs):
        # Automatically timestamp submission
        if self.status == self.Status.SUBMITTED and not self.submitted_at:
            self.submitted_at = timezone.now()

        # Run validation before saving
        self.full_clean()
        super().save(*args, **kwargs)

        # Snapshot version for audit history
        self.create_version_snapshot()

    def create_version_snapshot(self, actor=None):
        """Creates an immutable snapshot of this submission in SubmissionVersion."""
        latest_version = self.versions.order_by('-version_number').first()
        next_version = (latest_version.version_number + 1) if latest_version else 1

        SubmissionVersion.objects.create(
            submission=self,
            version_number=next_version,
            title=self.title,
            tagline=self.tagline,
            description=self.description,
            custom_answers=self.custom_answers,
            status=self.status,
            created_by=actor
        )


class SubmissionImage(models.Model):
    """
    Gallery images showcasing the submission (distinct from the primary thumbnail card image).
    Ordered sequentially to create a gallery carousel.
    """
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='gallery_images'
    )
    image = models.ImageField(
        upload_to='submissions/gallery/',
        help_text="Project gallery screenshot or diagram"
    )
    caption = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional descriptive caption for this screenshot"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in gallery view"
    )

    class Meta:
        verbose_name = "Submission Gallery Image"
        verbose_name_plural = "Submission Gallery Images"
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['submission', 'order']),
        ]

    def __str__(self):
        cap = f" - {self.caption}" if self.caption else ""
        return f"{self.submission.title} Gallery Image #{self.order}{cap}"


class SubmissionVersion(models.Model):
    """
    Immutable historical audit snapshot of a submission across draft iterations and edits.
    """
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.PositiveIntegerField(help_text="Sequential version number")
    title = models.CharField(max_length=255)
    tagline = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    custom_answers = models.JSONField(default=dict)
    status = models.CharField(max_length=20)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submission_versions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Submission Version"
        verbose_name_plural = "Submission Versions"
        ordering = ['-version_number']
        constraints = [
            models.UniqueConstraint(
                fields=['submission', 'version_number'],
                name='unique_submission_version'
            )
        ]

    def __str__(self):
        return f"{self.submission.title} (v{self.version_number})"
