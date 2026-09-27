"""
Comprehensive tests for Dogfood 2026 T2 Judging Engine:
1. Judge assignment algorithm (pure function, synthetic dataset: 10 judges, 20 submissions, balance and COI exclusion).
2. Role isolation API security (Judge B attempting GET /api/submissions/{id}/scores/ gets HTTP 403 Forbidden; Organizer gets 200).
3. Scoring interface and judging window closure enforcement.
4. Z-score normalization pipeline & rank delta tracking.
"""

from datetime import timedelta
from decimal import Decimal
from collections import Counter
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

from events.models import Event, EventRole
from teams.models import Team, TeamMembership
from submissions.models import Submission
from judging.models import Rubric, RubricCriterion, JudgeAssignment, Score, NormalizedScore
from judging.services.assignment import assign_judges, run_event_judge_assignments
from judging.services.normalization import run_score_normalization


class JudgeAssignmentAlgorithmTests(TestCase):
    """Unit tests for the pure algorithmic assignment function."""

    def test_pure_assignment_algorithm_balance_and_coi(self):
        """
        Synthetic test: 10 judges (IDs 1-10), 20 submissions (IDs 101-120), K=3.
        Assert:
        - Exactly 3 distinct judges per submission.
        - Total assignments = 60.
        - Workload is evenly balanced across judges (each judge gets exactly 6 assignments).
        - Conflict of interest exclusions are strictly respected.
        """
        judges = list(range(1, 11))  # 10 judges
        submissions = list(range(101, 121))  # 20 submissions
        k = 3

        # Introduce Conflict of Interest exclusions:
        # Judge 1 is on submission 101's team
        # Judge 2 is on submission 102's team
        # Judge 5 is on submissions 105, 106, 107
        exclusions = {
            101: {1},
            102: {2},
            105: {5},
            106: {5},
            107: {5},
        }

        assignments = assign_judges(
            judges=judges,
            submissions=submissions,
            k=k,
            exclusions=exclusions
        )

        # 1. Total assignments count check (20 submissions * 3 judges = 60)
        self.assertEqual(len(assignments), 60)

        # 2. Check each submission has exactly K distinct judges
        sub_to_judges = {}
        for j_id, s_id in assignments:
            sub_to_judges.setdefault(s_id, set()).add(j_id)

        for s_id in submissions:
            assigned_set = sub_to_judges[s_id]
            self.assertEqual(len(assigned_set), k, f"Submission {s_id} did not get {k} distinct judges.")

        # 3. Check COI exclusion is 100% respected
        self.assertNotIn(1, sub_to_judges[101], "COI violation: Judge 1 assigned to submission 101")
        self.assertNotIn(2, sub_to_judges[102], "COI violation: Judge 2 assigned to submission 102")
        self.assertNotIn(5, sub_to_judges[105], "COI violation: Judge 5 assigned to submission 105")
        self.assertNotIn(5, sub_to_judges[106], "COI violation: Judge 5 assigned to submission 106")
        self.assertNotIn(5, sub_to_judges[107], "COI violation: Judge 5 assigned to submission 107")

        # 4. Check workload balance
        judge_workloads = Counter(j_id for j_id, s_id in assignments)
        loads = [judge_workloads[j] for j in judges]
        min_load = min(loads)
        max_load = max(loads)

        # With 60 assignments and 10 judges, ideal is 6 per judge.
        # Even with COI exclusions, max difference should never exceed 1.
        self.assertLessEqual(max_load - min_load, 1, f"Workloads not balanced: min={min_load}, max={max_load}")
        self.assertTrue(all(load in (5, 6, 7) for load in loads))


class RoleIsolationAPITests(TestCase):
    """
    CRUCIAL ACCEPTANCE TEST:
    Judge A scores submission X.
    Judge B queries GET /api/submissions/{X}/scores/ -> Must return 403 Forbidden!
    Organizer queries GET /api/submissions/{X}/scores/ -> Must return 200 with full visibility.
    """

    def setUp(self):
        self.organizer = User.objects.create_user(username='org_dan', password='password123')
        self.judge_a = User.objects.create_user(username='judge_ann', password='password123')
        self.judge_b = User.objects.create_user(username='judge_bob', password='password123')
        self.hacker = User.objects.create_user(username='hacker_hal', password='password123')

        now = timezone.now()
        self.event = Event.objects.create(
            name="Security Event",
            slug="security-event",
            description="Testing judging isolation",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=3),
            submission_deadline=now + timedelta(days=1),
            voting_start=now - timedelta(hours=1),
            voting_end=now + timedelta(days=2),
            is_published=True,
            organizer=self.organizer
        )

        EventRole.objects.create(event=self.event, user=self.organizer, role=EventRole.Role.ORGANIZER)
        EventRole.objects.create(event=self.event, user=self.judge_a, role=EventRole.Role.JUDGE)
        EventRole.objects.create(event=self.event, user=self.judge_b, role=EventRole.Role.JUDGE)

        # Rubric & Criteria
        self.rubric = Rubric.objects.create(event=self.event, name="Security Rubric")
        self.criterion = RubricCriterion.objects.create(
            rubric=self.rubric,
            name="Robustness",
            weight=Decimal('100.00'),
            order=1
        )

        # Team & Submission X
        self.team = Team.objects.create(event=self.event, name="Crypto Guild", created_by=self.hacker)
        self.submission_x = Submission.objects.create(
            team=self.team,
            event=self.event,
            title="Encrypted Vault",
            description="Secure zero-knowledge storage",
            status=Submission.Status.SUBMITTED
        )

        # Judge A is assigned to submission X and scores it
        self.assignment_a = JudgeAssignment.objects.create(
            event=self.event,
            judge=self.judge_a,
            submission=self.submission_x,
            status=JudgeAssignment.Status.COMPLETED,
            completed_at=now
        )
        Score.objects.create(
            assignment=self.assignment_a,
            criterion=self.criterion,
            value=5,
            feedback="Masterful cryptography."
        )

        # Judge B is assigned to submission X (or not assigned), but has not scored yet
        self.assignment_b = JudgeAssignment.objects.create(
            event=self.event,
            judge=self.judge_b,
            submission=self.submission_x,
            status=JudgeAssignment.Status.ASSIGNED
        )

    def test_judge_cannot_view_scores_on_submission_returns_403(self):
        """
        Judge B attempts to GET /api/submissions/{id}/scores/.
        Must return 403 Forbidden (not 200 with hidden/empty data).
        """
        client = Client()
        client.login(username='judge_bob', password='password123')

        url = f"/api/submissions/{self.submission_x.id}/scores/"
        response = client.get(url)

        # Must be a real denial
        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    def test_organizer_can_view_all_submission_scores_returns_200(self):
        """
        Organizer attempts to GET /api/submissions/{id}/scores/.
        Must return 200 with full visibility into all judge scores.
        """
        client = Client()
        client.login(username='org_dan', password='password123')

        url = f"/api/submissions/{self.submission_x.id}/scores/"
        response = client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)  # Two assignments (Judge A and Judge B)

        # Verify Judge A's score is visible to organizer
        judge_a_entry = next((e for e in data if e['judge_username'] == 'judge_ann'), None)
        self.assertIsNotNone(judge_a_entry)
        self.assertEqual(judge_a_entry['scores'][0]['value'], 5)
        self.assertEqual(judge_a_entry['scores'][0]['feedback'], "Masterful cryptography.")

    def test_my_assignments_endpoint_isolates_judge_data(self):
        """
        Judge A queries /api/events/{id}/my-assignments/ and sees only their own assignment.
        """
        client = Client()
        client.login(username='judge_ann', password='password123')

        url = f"/api/events/{self.event.id}/my-assignments/"
        response = client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], self.assignment_a.id)
        self.assertEqual(data[0]['my_scores'][0]['value'], 5)

    def test_judge_progress_endpoint_restricts_non_organizers(self):
        """Non-organizers querying /api/events/{id}/judge-progress/ get 403 Forbidden."""
        client = Client()
        client.login(username='judge_ann', password='password123')
        url = f"/api/events/{self.event.id}/judge-progress/"
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

        # Organizer gets 200
        client.login(username='org_dan', password='password123')
        response_org = client.get(url)
        self.assertEqual(response_org.status_code, 200)
        self.assertEqual(response_org.json()['total_judges'], 2)


    def test_judging_window_closure_rejects_scoring(self):
        """Scoring after event.voting_end is rejected."""
        # Set voting_end to past
        self.event.voting_end = timezone.now() - timedelta(hours=1)
        self.event.save()

        client = Client()
        client.login(username='judge_bob', password='password123')
        url = reverse('judging:score_submission', kwargs={'assignment_id': self.assignment_b.id})

        response = client.post(url, {
            f"criterion_{self.criterion.id}": 4,
            f"feedback_{self.criterion.id}": "Late score"
        })
        self.assertEqual(response.status_code, 403)


class NormalizationServiceTests(TestCase):
    """Test z-score normalization mathematically balances harsh vs lenient judges."""

    def setUp(self):
        self.org = User.objects.create_user(username='norm_org', password='password123')
        self.harsh_judge = User.objects.create_user(username='judge_harsh', password='password123')
        self.lenient_judge = User.objects.create_user(username='judge_lenient', password='password123')

        now = timezone.now()
        self.event = Event.objects.create(
            name="Normalization Event",
            slug="normalization-event",
            description="Testing z-score normalization",
            start_date=now - timedelta(days=2),
            end_date=now + timedelta(days=2),
            submission_deadline=now - timedelta(hours=2),
            voting_start=now - timedelta(hours=2),
            voting_end=now + timedelta(days=1),
            is_published=True,
            organizer=self.org
        )

        self.rubric = Rubric.objects.create(event=self.event, name="Standard Rubric")
        self.c1 = RubricCriterion.objects.create(rubric=self.rubric, name="Execution", weight=Decimal('100.00'))

        team_1 = Team.objects.create(event=self.event, name="Team One", created_by=self.org)
        team_2 = Team.objects.create(event=self.event, name="Team Two", created_by=self.org)

        self.sub_1 = Submission.objects.create(team=team_1, event=self.event, title="Project 1", description="P1", status=Submission.Status.SUBMITTED)
        self.sub_2 = Submission.objects.create(team=team_2, event=self.event, title="Project 2", description="P2", status=Submission.Status.SUBMITTED)

        # Harsh judge evaluates both projects with ratings 1 and 2
        a_h1 = JudgeAssignment.objects.create(event=self.event, judge=self.harsh_judge, submission=self.sub_1, status=JudgeAssignment.Status.COMPLETED)
        Score.objects.create(assignment=a_h1, criterion=self.c1, value=1)

        a_h2 = JudgeAssignment.objects.create(event=self.event, judge=self.harsh_judge, submission=self.sub_2, status=JudgeAssignment.Status.COMPLETED)
        Score.objects.create(assignment=a_h2, criterion=self.c1, value=2)

        # Lenient judge evaluates both projects with ratings 4 and 5
        a_l1 = JudgeAssignment.objects.create(event=self.event, judge=self.lenient_judge, submission=self.sub_1, status=JudgeAssignment.Status.COMPLETED)
        Score.objects.create(assignment=a_l1, criterion=self.c1, value=4)

        a_l2 = JudgeAssignment.objects.create(event=self.event, judge=self.lenient_judge, submission=self.sub_2, status=JudgeAssignment.Status.COMPLETED)
        Score.objects.create(assignment=a_l2, criterion=self.c1, value=5)

    def test_zscore_normalization_execution(self):
        """Run normalization and assert scores are persisted in NormalizedScore table."""
        res = run_score_normalization(self.event)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['submission_count'], 2)

        # Verify database records
        ns_1 = NormalizedScore.objects.get(submission=self.sub_1, method='zscore')
        ns_2 = NormalizedScore.objects.get(submission=self.sub_2, method='zscore')

        self.assertIsNotNone(ns_1.normalized_value)
        self.assertIsNotNone(ns_2.normalized_value)

        # Project 2 was preferred by both judges (scored 2 vs 1, and 5 vs 4), so it should rank higher
        self.assertGreater(ns_2.normalized_value, ns_1.normalized_value)
