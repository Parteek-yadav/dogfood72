"""
Management command to run cross-judge score normalization and print
a reproducible Before/After diagnostic summary for JUDGING.md evidence.
"""

from django.core.management.base import BaseCommand, CommandError
from events.models import Event
from judging.services.normalization import run_score_normalization


class Command(BaseCommand):
    help = "Compute z-score normalization across judges and print before/after ranking diagnostics."

    def add_arguments(self, parser):
        parser.add_argument(
            '--event',
            type=int,
            required=True,
            help="Primary Key (ID) of the target Event."
        )

    def handle(self, *args, **options):
        event_id = options['event']
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event with ID {event_id} does not exist.")

        self.stdout.write(self.style.NOTICE(f"\n================================================================================"))
        self.stdout.write(self.style.NOTICE(f"  CROSS-JUDGE SCORE NORMALIZATION ENGINE (z-score standardization)  "))
        self.stdout.write(self.style.NOTICE(f"  Event: {event.name} (ID: {event.id})"))
        self.stdout.write(self.style.NOTICE(f"================================================================================\n"))

        res = run_score_normalization(event)

        if res.get('status') == 'no_scores':
            self.stdout.write(self.style.WARNING(f"WARNING: {res['message']}"))
            return

        # 1. Statistical Summary
        self.stdout.write(self.style.SUCCESS("--- STATISTICAL VARIANCE SUMMARY ---"))
        self.stdout.write(f"Total Judges Evaluated        : {res['judge_count']}")
        self.stdout.write(f"Total Submissions Evaluated   : {res['submission_count']}")
        self.stdout.write(f"Total Individual Score Records: {res['total_scores_evaluated']}")
        self.stdout.write(f"Global Raw Mean Score         : {res['grand_mean']:.3f} / 5.000")
        self.stdout.write(f"Global Score Standard Dev     : {res['grand_std']:.3f}")
        self.stdout.write(f"Inter-Judge Raw Mean Std Dev  : {res['judge_raw_std']:.3f}")
        self.stdout.write("\n")

        # 2. Before / After Leaderboard Table
        self.stdout.write(self.style.SUCCESS("--- SUBMISSION RANKINGS: RAW VS NORMALIZED ---"))
        header = f"{'Raw Rk':<7} | {'Norm Rk':<7} | {'Delta':<7} | {'Raw Mean':<9} | {'Z-Score Norm':<12} | {'Team':<20} | {'Submission Title'}"
        divider = "-" * len(header)
        self.stdout.write(divider)
        self.stdout.write(header)
        self.stdout.write(divider)

        rankings = res['rankings']
        for r in rankings:
            delta = r['rank_delta']
            if delta > 0:
                delta_str = f"+{delta} UP"
            elif delta < 0:
                delta_str = f"{delta} DN"
            else:
                delta_str = " 0 EQ"

            line = (
                f"#{r['raw_rank']:<6} | "
                f"#{r['norm_rank']:<6} | "
                f"{delta_str:<7} | "
                f"{r['raw_mean']:<9.3f} | "
                f"{r['normalized_score']:<12.3f} | "
                f"{r['team_name'][:18]:<20} | "
                f"{r['title']}"
            )
            self.stdout.write(line)

        self.stdout.write(divider)
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully stored {len(rankings)} normalized scores in NormalizedScore table."))
        self.stdout.write("Audit log persisted with action='judging.normalization_computed'.\n")
