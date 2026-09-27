"""
Accounts data models for Dogfood 2026.

ROLE MODELING JUSTIFICATION:
----------------------------
In Dogfood 2026 and real-world multi-event hackathon platforms (e.g., Devpost, Kaggle),
user roles operate at two distinct tiers:
1. 'visitor': An unauthenticated client with no database record.
2. 'admin': A platform-wide administrator (handled via Django's User.is_staff / User.is_superuser).
3. 'organizer', 'judge', 'participant': These roles are inherently PER-EVENT memberships.
   A user can plausibly be a Judge in Hackathon A, a Participant submitting a project in Hackathon B,
   and an Organizer managing Hackathon C. Locking a user to a single global role on their User model
   would artificially block this valid multi-event behavior.

Therefore:
- We extend Django's built-in User model via a OneToOne Profile model for platform-level
  identity and personal links (bio, avatar, GitHub handle, etc.).
- Per-event authorization is modeled via `events.EventRole` (and related team/judge assignments),
  enabling clean, scalable multi-tenancy across events.
"""

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    """
    User profile extending Django's built-in User model.
    Stores personal information, social links, and platform-level preferences.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    bio = models.TextField(blank=True, help_text="Short bio of the user")
    avatar = models.ImageField(
        upload_to='profiles/avatars/',
        blank=True,
        null=True,
        help_text="User profile avatar image"
    )
    github_handle = models.CharField(
        max_length=100,
        blank=True,
        help_text="GitHub username"
    )
    linkedin_url = models.URLField(blank=True, help_text="LinkedIn profile URL")
    website_url = models.URLField(blank=True, help_text="Personal website or portfolio URL")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username}'s Profile"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Automatically create or save the user profile when a User is created."""
    if created:
        Profile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
