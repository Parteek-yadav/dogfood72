"""
Voting and Community Discussion data models for Dogfood 2026.

VOTING RECONCILIATION DESIGN NOTE:
----------------------------------
To reconcile authenticated voting with anonymous link-based voting while strictly preventing
duplicate votes, the `Vote` model employs a dual-constraint strategy:
1. Authenticated Votes:
   - `user` is populated.
   - Enforced by a partial unique constraint: (submission, user) WHERE user IS NOT NULL.
   - A logged-in user can vote at most once per submission.

2. Anonymous Votes:
   - `user` is NULL.
   - A cryptographically signed token (Django TimestampSigner / HMAC cookie) is generated and
     sent to the client browser on their first visit.
   - When voting anonymously, the client submits the verified token, which is stored in `voter_token`.
   - Enforced by a partial unique constraint: (submission, voter_token) WHERE voter_token IS NOT NULL.
   - Optional `ip_hash` stores a salted SHA256 of the client IP for bot/sybil rate-limiting.

3. Quadratic Voting Support:
   - `weight` stores the vote credit (default 1.00), ready for square-root / credit-allocation
     quadratic voting tally engines.
"""

from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class Vote(models.Model):
    """
    Public or participant vote cast for a Submission.
    Supports authenticated users, signed anonymous voter tokens, and quadratic vote weights.
    """
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='votes'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='votes',
        help_text="Authenticated user casting this vote (null for anonymous link votes)"
    )
    voter_token = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="Cryptographically signed browser token for anonymous voting duplicate prevention"
    )
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Vote credit weight (default 1.00; allows quadratic voting calculations)"
    )
    ip_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Salted SHA256 of client IP address for abuse prevention"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Vote"
        verbose_name_plural = "Votes"
        ordering = ['-created_at']
        constraints = [
            # Ensure an authenticated user can only vote once per submission
            models.UniqueConstraint(
                fields=['submission', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_authenticated_submission_vote'
            ),
            # Ensure an anonymous token can only vote once per submission
            models.UniqueConstraint(
                fields=['submission', 'voter_token'],
                condition=models.Q(voter_token__isnull=False),
                name='unique_anonymous_submission_vote'
            ),
        ]
        indexes = [
            models.Index(fields=['submission', 'created_at']),
        ]

    def __str__(self):
        voter_desc = self.user.username if self.user else f"Anonymous ({self.voter_token[:8]}...)"
        return f"Vote for {self.submission.title} by {voter_desc} (weight {self.weight})"

    def clean(self):
        super().clean()
        if not self.user and not self.voter_token:
            raise ValidationError("A vote must have either an authenticated user or a signed anonymous voter token.")


class Comment(models.Model):
    """
    Public feedback / discussion comment on a Submission by a registered User.
    """
    submission = models.ForeignKey(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='comments'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='submission_comments'
    )
    body = models.TextField(help_text="Comment text")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Comment"
        verbose_name_plural = "Comments"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['submission', 'created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.user.username} on {self.submission.title} ({self.created_at:%Y-%m-%d})"
