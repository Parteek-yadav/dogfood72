"""
Management command to seed initial database fixtures for Dogfood 2026.
Supports loading official fixtures.json idempotently, or seeding high-fidelity
event data matching the official acceptance checker specifications:
- Event: evt_01 with submissions_close in the past
- Four checker users: organizer, judge_a, judge_b, participant
- Pre-populated Django session table rows with fixed session keys
- Prints the 4 Cookie: sessionid=<key> headers on boot
- Edge cases: zero-variance judge, missing scores / unfinished batches, duplicate submission
"""

import json
import os
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.utils import timezone
from django.conf import settings

from events.models import Event, EventRole, Track, Prize, CustomQuestion
from teams.models import Team, TeamMembership
from submissions.models import Submission
from judging.models import Rubric, RubricCriterion, JudgeAssignment, Score
from judging.services.assignment import assign_judges


CHECKER_SESSIONS = {
    'organizer': 'session_organizer_key',
    'judge_a': 'session_judge_a_key',
    'judge_b': 'session_judge_b_key',
    'participant': 'session_participant_key',
}


def create_fixed_session(user, session_key):
    """Create a persistent session row in django_session table with a fixed key."""
    s = SessionStore()
    session_data = {
        SESSION_KEY: str(user.pk),
        BACKEND_SESSION_KEY: 'django.contrib.auth.backends.ModelBackend',
        HASH_SESSION_KEY: user.get_session_auth_hash(),
    }
    encoded = s.encode(session_data)
    expire_date = timezone.now() + timedelta(days=90)
    Session.objects.filter(session_key=session_key).delete()
    Session.objects.create(
        session_key=session_key,
        session_data=encoded,
        expire_date=expire_date
    )


class Command(BaseCommand):
    help = "Seed database fixtures for Dogfood 2026 and acceptance checker."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Dogfood 2026 database fixtures...")

        fixtures_path = os.path.join(settings.BASE_DIR, 'fixtures.json')
        if os.path.exists(fixtures_path):
            self.stdout.write(f"Found {fixtures_path}, loading from file...")
            self.load_from_json(fixtures_path)
        else:
            self.stdout.write("fixtures.json not found on disk, seeding specification fixture environment...")
            self.load_default_fixtures()

        self.print_checker_headers()

    def print_checker_headers(self):
        self.stdout.write("\n=======================================================")
        self.stdout.write("  ACCEPTANCE CHECKER AUTHENTICATION HEADERS (Cookie)   ")
        self.stdout.write("=======================================================")
        for role, key in CHECKER_SESSIONS.items():
            self.stdout.write(f"Cookie: sessionid={key}")
        self.stdout.write("=======================================================\n")

    def load_default_fixtures(self):
        now = timezone.now()

        # 1. Admin user
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@dogfood2026.internal', 'is_staff': True, 'is_superuser': True}
        )
        admin_user.set_password('admin123')
        admin_user.save()

        # 2. Four checker accounts
        organizer, _ = User.objects.get_or_create(
            username='organizer',
            defaults={'email': 'organizer@dogfood2026.internal'}
        )
        organizer.set_password('password123')
        organizer.save()

        judge_a, _ = User.objects.get_or_create(
            username='judge_a',
            defaults={'email': 'judge_a@dogfood2026.internal'}
        )
        judge_a.set_password('password123')
        judge_a.save()

        judge_b, _ = User.objects.get_or_create(
            username='judge_b',
            defaults={'email': 'judge_b@dogfood2026.internal'}
        )
        judge_b.set_password('password123')
        judge_b.save()

        participant, _ = User.objects.get_or_create(
            username='participant',
            defaults={'email': 'participant@dogfood2026.internal'}
        )
        participant.set_password('password123')
        participant.save()

        # 3. Create fixed Django sessions for the 4 checker users
        create_fixed_session(organizer, CHECKER_SESSIONS['organizer'])
        create_fixed_session(judge_a, CHECKER_SESSIONS['judge_a'])
        create_fixed_session(judge_b, CHECKER_SESSIONS['judge_b'])
        create_fixed_session(participant, CHECKER_SESSIONS['participant'])

        # 4. Primary Event (evt_01)
        # Note: submission_deadline is set in the past so post-deadline checks reject submissions
        event, _ = Event.objects.get_or_create(
            slug='evt_01',
            defaults={
                'name': 'Dogfood 2026 Invitational',
                'description': 'The official 72-hour engineering sprint event evt_01.',
                'start_date': now - timedelta(days=3),
                'end_date': now + timedelta(days=2),
                'submission_deadline': now - timedelta(hours=3),
                'voting_start': now - timedelta(hours=3),
                'voting_end': now + timedelta(days=1),
                'is_published': True,
                'organizer': organizer,
            }
        )
        event.is_published = True
        event.save()

        # Event roles for the 4 checker users
        EventRole.objects.get_or_create(event=event, user=organizer, role=EventRole.Role.ORGANIZER)
        EventRole.objects.get_or_create(event=event, user=judge_a, role=EventRole.Role.JUDGE)
        EventRole.objects.get_or_create(event=event, user=judge_b, role=EventRole.Role.JUDGE)
        EventRole.objects.get_or_create(event=event, user=participant, role=EventRole.Role.PARTICIPANT)

        # 5. Tracks
        t_ai, _ = Track.objects.get_or_create(event=event, name='AI Agents & Autonomous Systems')
        t_infra, _ = Track.objects.get_or_create(event=event, name='Developer Infrastructure & Tooling')
        t_sec, _ = Track.objects.get_or_create(event=event, name='Security & Cryptographic Systems')
        tracks = [t_ai, t_infra, t_sec]

        # 6. Rubric & Criteria
        rubric, _ = Rubric.objects.get_or_create(
            event=event,
            defaults={'name': 'Dogfood 2026 Official Rubric', 'description': 'Standardized 1-5 evaluation rubric.'}
        )
        crit_tech, _ = RubricCriterion.objects.get_or_create(rubric=rubric, name='Technical Execution', defaults={'weight': Decimal('40.00'), 'order': 1})
        crit_inno, _ = RubricCriterion.objects.get_or_create(rubric=rubric, name='Innovation & Creativity', defaults={'weight': Decimal('30.00'), 'order': 2})
        crit_ux, _ = RubricCriterion.objects.get_or_create(rubric=rubric, name='Polish & Developer Experience', defaults={'weight': Decimal('30.00'), 'order': 3})
        criteria = [crit_tech, crit_inno, crit_ux]

        # 7. Additional Judges (~30 judges total)
        judges = [judge_a, judge_b]
        for i in range(1, 29):
            u_judge, _ = User.objects.get_or_create(
                username=f"judge_{i:02d}",
                defaults={'email': f"judge_{i:02d}@dogfood.internal"}
            )
            u_judge.set_password('password123')
            u_judge.save()
            EventRole.objects.get_or_create(event=event, user=u_judge, role=EventRole.Role.JUDGE)
            judges.append(u_judge)

        # 8. Seed Projects (~40 projects)
        project_titles = [
            "AutoDev Copilot", "HyperChain DB", "NeuralMesh", "KubeDeployer", "QuantumQuery",
            "OmniRoute Engine", "DataPulse AI", "ByteFlow", "CipherVault", "StreamGrid",
            "GraphWhisperer", "EdgeSentinel", "AuraVision", "SynapseNet", "VortexCache",
            "PrismKernel", "CloudForge", "LogHarbor", "FleetSync", "MetricForge",
            "HelixGuard", "PixelWeaver", "VectorBridge", "TerraNode", "ApexRegistry",
            "NovaCompute", "ZeroTrust Gateway", "IronClad Auth", "Skyline Analytics", "DeepInspect",
            "CoreTensor", "OmniMesh", "ArgusMonitor", "KryptonDB", "PulseWorker",
            "ChronoTrace", "FalconQueue", "StratumFS", "AeroLoad", "ZenithOps"
        ]

        submissions = []
        for idx, title in enumerate(project_titles, start=1):
            team_name = f"team_{title.lower().replace(' ', '_').replace('-', '_')}"
            hacker, _ = User.objects.get_or_create(
                username=f"{team_name}_lead",
                defaults={'email': f"{team_name}@dogfood.internal"}
            )
            hacker.set_password('password123')
            hacker.save()

            team, _ = Team.objects.get_or_create(event=event, name=team_name, defaults={'created_by': hacker})
            TeamMembership.objects.get_or_create(team=team, user=hacker, defaults={'role': TeamMembership.Role.LEADER})
            EventRole.objects.get_or_create(event=event, user=hacker, role=EventRole.Role.PARTICIPANT)

            sub, _ = Submission.objects.get_or_create(
                team=team,
                event=event,
                defaults={
                    'title': title,
                    'tagline': f"Next-generation solution for {title}",
                    'description': f"Comprehensive writeup and architecture documentation for project {title}.",
                    'track': tracks[(idx - 1) % len(tracks)],
                    'status': Submission.Status.SUBMITTED,
                    'submitted_at': now - timedelta(hours=4),
                    'tech_tags': ['Python', 'Django', 'PostgreSQL', 'Docker'],
                    'repo_url': f"https://github.com/dogfood-2026/{team_name}",
                    'live_url': f"https://example.com/demo/{team_name}",
                }
            )
            submissions.append(sub)

        # 9. Edge Case: Duplicate submission (keep it, flag it for organizer)
        dup_team, _ = Team.objects.get_or_create(event=event, name="team_duplicate_entry", defaults={'created_by': participant})
        TeamMembership.objects.get_or_create(team=dup_team, user=participant, defaults={'role': TeamMembership.Role.LEADER})
        dup_sub, _ = Submission.objects.get_or_create(
            team=dup_team,
            event=event,
            defaults={
                'title': "AutoDev Copilot",  # Duplicate title
                'tagline': "[FLAGGED DUPLICATE] Duplicate submission entry for organizer review",
                'description': "Flagged duplicate submission for organizer review.",
                'track': t_ai,
                'status': Submission.Status.SUBMITTED,
                'submitted_at': now - timedelta(hours=5),
                'custom_answers': {},
            }
        )

        # 10. Run Balanced Judge Assignments (K=3)
        judge_ids = [j.id for j in judges]
        sub_ids = [s.id for s in submissions]
        assignment_pairs = assign_judges(judge_ids, sub_ids, k=3)

        for j_id, s_id in assignment_pairs:
            judge_user = next(j for j in judges if j.id == j_id)
            sub_obj = next(s for s in submissions if s.id == s_id)

            assign, _ = JudgeAssignment.objects.get_or_create(
                event=event,
                judge=judge_user,
                submission=sub_obj,
                defaults={'status': JudgeAssignment.Status.COMPLETED, 'completed_at': now}
            )

            # Edge Case 1: Judge who scored everything identically (zero-variance judge: judge_01 always gives 3)
            if judge_user.username == 'judge_01':
                for crit in criteria:
                    Score.objects.update_or_create(
                        assignment=assign,
                        criterion=crit,
                        defaults={'value': 3, 'feedback': "Standard evaluation score 3."}
                    )
                continue

            # Edge Case 2: Unfinished review batches / missing scores (judge_02 leaves assignments in_progress)
            if judge_user.username == 'judge_02':
                assign.status = JudgeAssignment.Status.IN_PROGRESS
                assign.save()
                # Score only first criterion, leave others missing
                Score.objects.update_or_create(
                    assignment=assign,
                    criterion=crit_tech,
                    defaults={'value': 4, 'feedback': "Work in progress."}
                )
                continue

            # Standard scoring: deterministic pattern based on submission and judge IDs
            base_val = 3 + ((s_id + j_id) % 3)  # 3, 4, or 5
            for crit_idx, crit in enumerate(criteria):
                val = max(1, min(5, base_val + (crit_idx % 2 - 1)))
                Score.objects.update_or_create(
                    assignment=assign,
                    criterion=crit,
                    defaults={'value': val, 'feedback': f"Evaluated by {judge_user.username} for {crit.name}"}
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded event '{event.slug}' ({event.name}) with {len(judges)} judges, "
                f"{len(submissions)} submissions, and {len(assignment_pairs)} assignments."
            )
        )

    def load_from_json(self, filepath):
        """Loads fixtures.json idempotently if present."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        now = timezone.now()
        event_data = data.get('event', {})
        event_slug = event_data.get('slug', event_data.get('id', 'evt_01'))
        event_name = event_data.get('name', 'Dogfood 2026 Event')

        organizer, _ = User.objects.get_or_create(username='organizer', defaults={'email': 'organizer@dogfood.internal'})
        organizer.set_password('password123')
        organizer.save()

        # Parse close date
        close_str = event_data.get('submissions_close') or event_data.get('submission_deadline')
        close_date = timezone.datetime.fromisoformat(close_str) if close_str else (now - timedelta(hours=2))

        event, _ = Event.objects.get_or_create(
            slug=event_slug,
            defaults={
                'name': event_name,
                'description': event_data.get('description', 'Official event from fixtures.json'),
                'start_date': now - timedelta(days=2),
                'end_date': now + timedelta(days=2),
                'submission_deadline': close_date,
                'voting_start': close_date,
                'voting_end': now + timedelta(days=1),
                'is_published': True,
                'organizer': organizer
            }
        )
        event.submission_deadline = close_date
        event.is_published = True
        event.save()
        EventRole.objects.get_or_create(event=event, user=organizer, role=EventRole.Role.ORGANIZER)

        # Seed checker users and fixed sessions
        for uname in ['judge_a', 'judge_b', 'participant']:
            u, _ = User.objects.get_or_create(username=uname, defaults={'email': f"{uname}@dogfood.internal"})
            u.set_password('password123')
            u.save()
            role = EventRole.Role.JUDGE if 'judge' in uname else EventRole.Role.PARTICIPANT
            EventRole.objects.get_or_create(event=event, user=u, role=role)

        for rname, skey in CHECKER_SESSIONS.items():
            u = User.objects.get(username=rname)
            create_fixed_session(u, skey)

        self.stdout.write(self.style.SUCCESS(f"Loaded event {event_slug} from fixtures.json"))
