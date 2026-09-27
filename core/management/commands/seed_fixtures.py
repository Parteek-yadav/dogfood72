"""
Management command to seed initial fixtures for Dogfood 2026 hackathon platform.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed initial database fixtures (stub for now)"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("[seed_fixtures] Stub executed successfully (no-op). Ready for seed data.")
        )
