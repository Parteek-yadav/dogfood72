"""
Judging data models for Dogfood 2026.

RUBRIC WEIGHTING DECISION NOTE:
-------------------------------
Rubric criteria weights are specified as target percentages designed to sum to 100.00.
We enforce validation via `Rubric.validate_weight_sum()` while also computing normalized
relative weights `(weight / total_weight)` in the scoring pipeline so that evaluation
remains mathematically robust even if criteria weights are configured with alternative bases.
"""

from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError


class Rubric(models.Model):
    """
    Evaluation rubric established by organizers for an Event.
    Composed of one or more weighted criteria.
    """
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='rubrics'
    )
    name = models.CharField(max_length=255, help_text="Rubric title (e.g. 'General Technical Rubric')")
    description = models.TextField(blank=True, help_text="Guidelines and evaluation instructions for judges")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rubric"
        verbose_name_plural = "Rubrics"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.event.name})"

    def total_weight(self):
        return self.criteria.aggregate(total=models.Sum('weight'))['total'] or Decimal('0.00')

    def validate_weight_sum(self):
        """Validates that all criteria in this rubric sum to 100.00."""
        total = self.total_weight()
        if total != Decimal('100.00'):
            raise ValidationError(
                f"Rubric '{self.name}' criteria weights must sum to 100.00 (currently {total})."
            )


class RubricCriterion(models.Model):
    """
    Individual evaluation dimension within a Rubric (e.g. 'Innovation', 'Technical Polish').
    """
    rubric = models.ForeignKey(
        Rubric,
        on_delete=models.CASCADE,
        related_name='criteria'
    )
    name = models.CharField(max_length=255, help_text="Criterion name (e.g. 'Technical Execution')")
    description = models.TextField(blank=True, help_text="Scoring guide for 1-5 scale")
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('25.00'),
        help_text="Weight percentage (e.g. 25.00 for 25%). Rubric total should sum to 100.00."
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order in judging form")

    class Meta:
        verbose_name = "Rubric Criterion"
        verbose_name_plural = "Rubric Criteria"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.name} ({self.weight}%)"


class JudgeAssignment(models.Model):
    """
    Assignment of a specific Submission to an authenticated Judge user for evaluation.
    """
    class Status(models.TextChoices):
        ASSIGNED = 'assigned', 'Assigned'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'

    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='judge_assignments'
    )
    judge = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='judging_assignments'
    )
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='judge_assignments'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ASSIGNED,
        db_index=True
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Judge Assignment"
        verbose_name_plural = "Judge Assignments"
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['judge', 'submission'],
                name='unique_judge_submission_assignment'
            )
        ]
        indexes = [
            models.Index(fields=['event', 'judge', 'status']),
            models.Index(fields=['submission', 'status']),
        ]

    def __str__(self):
        return f"Judge {self.judge.username} -> {self.submission.title} [{self.get_status_display()}]"

    def clean(self):
        super().clean()
        if self.submission_id and self.event_id and self.submission.event_id != self.event_id:
            raise ValidationError({'submission': "Assigned submission must belong to the assigned event."})


class Score(models.Model):
    """
    Individual rating given by a Judge on a RubricCriterion for a JudgeAssignment.
    Values are integer ratings constrained to 1–5.
    """
    assignment = models.ForeignKey(
        JudgeAssignment,
        on_delete=models.CASCADE,
        related_name='scores'
    )
    criterion = models.ForeignKey(
        RubricCriterion,
        on_delete=models.CASCADE,
        related_name='scores'
    )
    value = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Score value between 1 and 5 (inclusive)"
    )
    feedback = models.TextField(blank=True, help_text="Optional feedback note from the judge for this criterion")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Score"
        verbose_name_plural = "Scores"
        constraints = [
            models.UniqueConstraint(
                fields=['assignment', 'criterion'],
                name='unique_assignment_criterion_score'
            )
        ]
        indexes = [
            models.Index(fields=['assignment', 'criterion']),
        ]

    def __str__(self):
        return f"{self.assignment.judge.username} - {self.criterion.name}: {self.value}/5"


class NormalizedScore(models.Model):
    """
    Persisted output of the score normalization pipeline (e.g. z-score calculation)
    to adjust for judge leniency/harshness variance. Ensures a deterministic and
    auditable trail for rankings.
    """
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='normalized_scores'
    )
    method = models.CharField(
        max_length=50,
        default='zscore',
        help_text="Normalization algorithm used (e.g. 'zscore', 'trimmed_mean', 'minmax')"
    )
    raw_mean = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        help_text="Unadjusted raw arithmetic mean score across judges"
    )
    normalized_value = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        help_text="Normalized score output used for official ranking"
    )
    computed_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this normalization record was computed"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Diagnostic stats (standard deviations, count of scores, judge IDs)"
    )

    class Meta:
        verbose_name = "Normalized Score"
        verbose_name_plural = "Normalized Scores"
        ordering = ['-normalized_value']
        constraints = [
            models.UniqueConstraint(
                fields=['submission', 'method'],
                name='unique_submission_normalization_method'
            )
        ]
        indexes = [
            models.Index(fields=['method', '-normalized_value']),
        ]

    def __str__(self):
        return f"{self.submission.title} - {self.method}: {self.normalized_value} (raw {self.raw_mean})"
