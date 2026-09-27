"""
Management command to seed initial database fixtures for Dogfood 2026.
Seeds realistic demo events, organizers, judges with varying leniency biases,
teams, submissions, rubrics, and evaluation scores.
"""

from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from events.models import Event, EventRole, Track, Prize, CustomQuestion
from teams.models import Team, TeamMembership
from submissions.models import Submission
from judging.models import Rubric, RubricCriterion, JudgeAssignment, Score
from judging.services.assignment import assign_judges


class Command(BaseCommand):
    help = "Seed initial database fixtures with realistic hackathon and judging data."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Dogfood 2026 initial fixtures...")

        # 1. Admin & Organizer
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@dogfood2026.internal', 'is_staff': True, 'is_superuser': True}
        )
        admin_user.set_password('admin123')
        admin_user.save()

        organizer, _ = User.objects.get_or_create(
            username='organizer_sam',
            defaults={'email': 'sam@dogfood2026.internal'}
        )
        organizer.set_password('password123')
        organizer.save()

        # 2. Event
        now = timezone.now()
        event, _ = Event.objects.get_or_create(
            slug='dogfood-2026',
            defaults={
                'name': 'Dogfood 2026 Invitational',
                'description': 'The premier 72-hour engineering sprint building against the dogfood spec.',
                'start_date': now - timedelta(days=2),
                'end_date': now + timedelta(days=2),
                'submission_deadline': now - timedelta(hours=2),
                'voting_start': now - timedelta(hours=2),
                'voting_end': now + timedelta(days=1),
                'is_published': True,
                'organizer': organizer
            }
        )
        EventRole.objects.get_or_create(event=event, user=organizer, role=EventRole.Role.ORGANIZER)

        # 3. Tracks & Prizes
        t1, _ = Track.objects.get_or_create(event=event, name='AI Agents & Autonomous Systems')
        t2, _ = Track.objects.get_or_create(event=event, name='Developer Infrastructure & Tooling')

        Prize.objects.get_or_create(event=event, name='Grand Prize', defaults={'amount': '$10,000 USD', 'rank': 1})
        Prize.objects.get_or_create(event=event, name='Runner Up', defaults={'amount': '$5,000 USD', 'rank': 2})
        Prize.objects.get_or_create(event=event, name='Best AI Agent', track=t1, defaults={'amount': '$2,500 USD', 'rank': 3})

        # 4. Custom Questions
        CustomQuestion.objects.get_or_create(
            event=event,
            label="What is the hardest engineering challenge you solved?",
            defaults={'field_type': CustomQuestion.FieldType.TEXTAREA, 'required': True, 'order': 1}
        )
        CustomQuestion.objects.get_or_create(
            event=event,
            label="Target Architecture",
            defaults={
                'field_type': CustomQuestion.FieldType.SELECT,
                'choices': ['Agentic Workflow', 'Microservices', 'Serverless', 'Monolith'],
                'required': False,
                'order': 2
            }
        )

        # 5. Rubric & Criteria
        rubric, _ = Rubric.objects.get_or_create(
            event=event,
            defaults={'name': 'Dogfood 2026 Official Rubric', 'description': 'Standardized 1-5 evaluation.'}
        )
        c_tech, _ = RubricCriterion.objects.get_or_create(rubric=rubric, name='Technical Execution', defaults={'weight': Decimal('40.00'), 'order': 1})
        c_inno, _ = RubricCriterion.objects.get_or_create(rubric=rubric, name='Innovation & Creativity', defaults={'weight': Decimal('30.00'), 'order': 2})
        c_ux, _ = RubricCriterion.objects.get_or_create(rubric=rubric, name='Polish & Developer Experience', defaults={'weight': Decimal('30.00'), 'order': 3})

        # 6. Judges with simulated rating personalities:
        # Judge 1: harsh_harry (scores low: 1-3)
        # Judge 2: lenient_lucy (scores high: 4-5)
        # Judge 3: balanced_bob (scores normal: 2-4)
        # Judge 4: strict_eve (scores rigorous: 2-4)
        judges = []
        for uname in ['harsh_harry', 'lenient_lucy', 'balanced_bob', 'strict_eve']:
            u, _ = User.objects.get_or_create(username=uname, defaults={'email': f"{uname}@dogfood.internal"})
            u.set_password('password123')
            u.save()
            EventRole.objects.get_or_create(event=event, user=u, role=EventRole.Role.JUDGE)
            judges.append(u)

        # 7. Teams & Submissions
        projects_data = [
            ("AutoDev Copilot", "Autonomous coding agent loop", t1, "team_autodev"),
            ("HyperChain DB", "Decentralized consensus store", t2, "team_hyperchain"),
            ("NeuralMesh", "Distributed agent communication mesh", t1, "team_neuralmesh"),
            ("KubeDeployer", "Zero-downtime micro-orchestration", t2, "team_kubedeploy"),
            ("QuantumQuery", "Vector embeddings graph search", t1, "team_quantum"),
        ]

        submissions = []
        for title, tagline, track, team_name in projects_data:
            lead_hacker, _ = User.objects.get_or_create(username=f"{team_name}_lead")
            lead_hacker.set_password('password123')
            lead_hacker.save()

            team, _ = Team.objects.get_or_create(event=event, name=team_name, defaults={'created_by': lead_hacker})
            TeamMembership.objects.get_or_create(team=team, user=lead_hacker, defaults={'role': TeamMembership.Role.LEADER})
            EventRole.objects.get_or_create(event=event, user=lead_hacker, role=EventRole.Role.PARTICIPANT)

            sub, _ = Submission.objects.get_or_create(
                team=team,
                event=event,
                defaults={
                    'title': title,
                    'tagline': tagline,
                    'description': f"Full writeup and architectural breakdown for {title}.",
                    'track': track,
                    'status': Submission.Status.SUBMITTED,
                    'submitted_at': now - timedelta(hours=3),
                    'tech_tags': ['Python', 'Django', 'PostgreSQL', 'Docker'],
                    'repo_url': f"https://github.com/dogfood-demo/{team_name}",
                    'live_url': f"https://demo.dogfood2026.internal/{team_name}",
                    'custom_answers': {
                        "1": "Scaling asynchronous worker coordination under high load.",
                        "2": "Agentic Workflow"
                    }
                }
            )
            submissions.append(sub)

        # 8. Run balanced judge assignments (K=3)
        judge_ids = [j.id for j in judges]
        sub_ids = [s.id for s in submissions]
        pairs = assign_judges(judge_ids, sub_ids, k=3)

        # 9. Seed scores with judge rating variance
        # harsh_harry: base -1
        # lenient_lucy: base +1
        base_ratings = {
            submissions[0].id: 4,  # AutoDev Copilot (strong)
            submissions[1].id: 3,  # HyperChain DB (medium)
            submissions[2].id: 5,  # NeuralMesh (exceptional)
            submissions[3].id: 2,  # KubeDeployer (weak)
            submissions[4].id: 4,  # QuantumQuery (strong)
        }

        criteria_list = [c_tech, c_inno, c_ux]

        for j_id, s_id in pairs:
            judge_user = next(j for j in judges if j.id == j_id)
            sub_obj = next(s for s in submissions if s.id == s_id)

            assign, _ = JudgeAssignment.objects.get_or_create(
                event=event,
                judge=judge_user,
                submission=sub_obj,
                defaults={'status': JudgeAssignment.Status.COMPLETED, 'completed_at': now}
            )
            assign.status = JudgeAssignment.Status.COMPLETED
            assign.save()

            base = base_ratings[s_id]
            if judge_user.username == 'harsh_harry':
                val = max(1, base - 1)
            elif judge_user.username == 'lenient_lucy':
                val = min(5, base + 1)
            elif judge_user.username == 'strict_eve':
                val = max(1, base - 1) if base > 3 else base
            else:
                val = base

            for crit in criteria_list:
                Score.objects.update_or_create(
                    assignment=assign,
                    criterion=crit,
                    defaults={'value': val, 'feedback': f"Evaluated by {judge_user.username}"}
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded '{event.name}' with {len(judges)} judges, "
                f"{len(submissions)} submissions, and {len(pairs)} completed score evaluations!"
            )
        )
