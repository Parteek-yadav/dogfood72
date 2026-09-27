"""
Core shared data models for Dogfood 2026.
"""

from django.db import models
from django.contrib.auth.models import User


class AuditLogEntry(models.Model):
    """
    Immutable audit log entry recording administrative, judging, submission,
    and system events. Easily queryable and visible to event organizers without
    needing direct database access.
    """
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="User who initiated this action (null for automated background/system tasks)"
    )
    action = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Action identifier (e.g. 'submission.created', 'score.submitted', 'rubric.updated')"
    )
    target_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Entity type being acted upon (e.g. 'Submission', 'Event', 'Score')"
    )
    target_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Primary key of the affected entity"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Contextual payload, before/after values, or event details"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the action occurred"
    )

    class Meta:
        verbose_name = "Audit Log Entry"
        verbose_name_plural = "Audit Log Entries"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {actor_name} -> {self.action} on {self.target_type}:{self.target_id}"

    @classmethod
    def log(cls, action, target, actor=None, metadata=None):
        """Helper utility method to record an audit log event."""
        target_type = target.__class__.__name__ if hasattr(target, '__class__') else str(target)
        target_id = str(getattr(target, 'pk', target))
        return cls.objects.create(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {}
        )
