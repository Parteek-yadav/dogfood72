"""
Management command to export judging datasets to CSV files or stdout.
Supported types: raw_scores, normalized_scores, judge_assignments, final_rankings.
"""

import csv
import sys
from django.core.management.base import BaseCommand, CommandError
from events.models import Event
from judging.models import Score, JudgeAssignment, NormalizedScore


class Command(BaseCommand):
    help = "Export judging datasets (raw_scores, normalized_scores, judge_assignments, final_rankings) to CSV."

    def add_arguments(self, parser):
        parser.add_argument('--event', type=int, required=True, help="Event ID")
        parser.add_argument(
            '--type',
            type=str,
            required=True,
            choices=['raw_scores', 'normalized_scores', 'judge_assignments', 'final_rankings'],
            help="Dataset type to export"
        )
        parser.add_argument('--output', type=str, default='', help="Optional file path to write CSV into (defaults to stdout)")

    def handle(self, *args, **options):
        event_id = options['event']
        export_type = options['type']
        output_path = options['output']

        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            raise CommandError(f"Event with ID {event_id} does not exist.")

        out = open(output_path, 'w', newline='', encoding='utf-8') if output_path else sys.stdout
        writer = csv.writer(out)

        try:
            if export_type == 'raw_scores':
                writer.writerow(['Submission ID', 'Submission Title', 'Team', 'Judge Username', 'Criterion', 'Weight', 'Score', 'Feedback', 'Timestamp'])
                scores = (
                    Score.objects.filter(assignment__event=event)
                    .select_related('assignment__submission__team', 'assignment__judge', 'criterion')
                    .order_by('assignment__submission__title', 'assignment__judge__username')
                )
                for s in scores:
                    writer.writerow([
                        s.assignment.submission_id,
                        s.assignment.submission.title,
                        s.assignment.submission.team.name,
                        s.assignment.judge.username,
                        s.criterion.name,
                        s.criterion.weight,
                        s.value,
                        s.feedback,
                        s.updated_at.isoformat()
                    ])

            elif export_type == 'normalized_scores':
                writer.writerow(['Rank', 'Submission ID', 'Submission Title', 'Team', 'Track', 'Raw Mean', 'Normalized Score', 'Computed At'])
                ns_qs = (
                    NormalizedScore.objects.filter(submission__event=event, method='zscore')
                    .select_related('submission__team', 'submission__track')
                    .order_by('-normalized_value')
                )
                for rank, ns in enumerate(ns_qs, start=1):
                    writer.writerow([
                        rank,
                        ns.submission_id,
                        ns.submission.title,
                        ns.submission.team.name,
                        ns.submission.track.name if ns.submission.track else '',
                        ns.raw_mean,
                        ns.normalized_value,
                        ns.computed_at.isoformat()
                    ])

            elif export_type == 'judge_assignments':
                writer.writerow(['Assignment ID', 'Judge Username', 'Submission Title', 'Team', 'Status', 'Assigned At', 'Completed At'])
                assigns = (
                    JudgeAssignment.objects.filter(event=event)
                    .select_related('judge', 'submission__team')
                    .order_by('judge__username', 'submission__title')
                )
                for a in assigns:
                    writer.writerow([
                        a.id,
                        a.judge.username,
                        a.submission.title,
                        a.submission.team.name,
                        a.status,
                        a.assigned_at.isoformat(),
                        a.completed_at.isoformat() if a.completed_at else ''
                    ])

            elif export_type == 'final_rankings':
                writer.writerow(['Rank', 'Submission Title', 'Team', 'Track', 'Raw Mean', 'Normalized Final Score'])
                ns_qs = (
                    NormalizedScore.objects.filter(submission__event=event, method='zscore')
                    .select_related('submission__team', 'submission__track')
                    .order_by('-normalized_value')
                )
                for rank, ns in enumerate(ns_qs, start=1):
                    writer.writerow([
                        rank,
                        ns.submission.title,
                        ns.submission.team.name,
                        ns.submission.track.name if ns.submission.track else 'General',
                        ns.raw_mean,
                        ns.normalized_value
                    ])

            if output_path:
                out.close()
                self.stdout.write(self.style.SUCCESS(f"Successfully exported {export_type} for '{event.name}' to {output_path}"))

        finally:
            if output_path and not out.closed:
                out.close()
