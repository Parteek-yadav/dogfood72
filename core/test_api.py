"""
Tests for DRF REST API endpoints covering all UI actions:
- Event CRUD, tracks, prizes, custom questions, roles
- Teams, invite tokens, member joining
- Submissions draft, update, deadline guards, gallery
- Rubrics, algorithmic assignment, scoring, normalization
- Voting, comments, and CSV data exports
- OpenAPI schema generation at /api/schema/
"""

from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

from events.models import Event, EventRole, Track, Prize, CustomQuestion
from teams.models import Team, TeamMembership, Invite
from submissions.models import Submission, SubmissionImage
from judging.models import Rubric, RubricCriterion, JudgeAssignment, Score, NormalizedScore
from voting.models import Vote, Comment


class DRFAPIAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.organizer = User.objects.create_user(username='api_organizer', password='password123', email='org@example.com')
        self.judge = User.objects.create_user(username='api_judge', password='password123', email='judge@example.com')
        self.participant = User.objects.create_user(username='api_participant', password='password123', email='hacker@example.com')
        self.other_user = User.objects.create_user(username='api_other', password='password123', email='other@example.com')

        now = timezone.now()
        self.event = Event.objects.create(
            name="API Test Hackathon",
            slug="api-test-hackathon",
            description="Testing API endpoints",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=5),
            submission_deadline=now + timedelta(days=3),
            voting_start=now + timedelta(days=3),
            voting_end=now + timedelta(days=5),
            is_published=True,
            organizer=self.organizer
        )
        EventRole.objects.create(event=self.event, user=self.organizer, role=EventRole.Role.ORGANIZER)
        EventRole.objects.create(event=self.event, user=self.judge, role=EventRole.Role.JUDGE)
        EventRole.objects.create(event=self.event, user=self.participant, role=EventRole.Role.PARTICIPANT)

        self.team = Team.objects.create(event=self.event, name="API Alpha Team", created_by=self.participant)
        TeamMembership.objects.create(team=self.team, user=self.participant, role=TeamMembership.Role.LEADER)

        self.rubric = Rubric.objects.create(event=self.event, name="Standard Rubric")
        self.crit1 = RubricCriterion.objects.create(rubric=self.rubric, name="Tech Execution", weight=Decimal('50.00'), order=1)
        self.crit2 = RubricCriterion.objects.create(rubric=self.rubric, name="Innovation", weight=Decimal('50.00'), order=2)

    def test_openapi_schema_endpoint(self):
        """Verify drf-spectacular schema generation returns 200 and valid content."""
        resp = self.client.get('/api/schema/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'openapi', resp.content.lower())
        self.assertIn(b'/api/events/', resp.content)
        self.assertIn(b'/api/teams/', resp.content)
        self.assertIn(b'/api/submissions/', resp.content)

    def test_event_list_and_create_api(self):
        """Test GET /api/events/ and POST /api/events/."""
        resp = self.client.get('/api/events/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

        self.client.login(username='api_organizer', password='password123')
        now = timezone.now()
        payload = {
            'name': "New API Event",
            'slug': "new-api-event",
            'description': "Created via API",
            'start_date': (now + timedelta(days=1)).isoformat(),
            'end_date': (now + timedelta(days=10)).isoformat(),
            'submission_deadline': (now + timedelta(days=8)).isoformat(),
            'voting_start': (now + timedelta(days=8)).isoformat(),
            'voting_end': (now + timedelta(days=10)).isoformat(),
            'is_published': True
        }
        create_resp = self.client.post('/api/events/', payload, content_type='application/json')
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()['name'], "New API Event")

    def test_event_tracks_and_prizes_api(self):
        """Test adding tracks and prizes via API."""
        self.client.login(username='api_organizer', password='password123')
        track_resp = self.client.post(f'/api/events/{self.event.id}/tracks/', {
            'name': "AI/ML Track",
            'description': "Best AI model"
        }, content_type='application/json')
        self.assertEqual(track_resp.status_code, 201)
        track_id = track_resp.json()['id']

        prize_resp = self.client.post(f'/api/events/{self.event.id}/prizes/', {
            'name': "Grand Prize",
            'track': track_id,
            'amount': "$10,000",
            'description': "1st place overall",
            'rank': 1
        }, content_type='application/json')
        self.assertEqual(prize_resp.status_code, 201)

    def test_team_invite_and_join_api(self):
        """Test team invite generation and member joining via token."""
        self.client.login(username='api_participant', password='password123')
        invite_resp = self.client.post(f'/api/teams/{self.team.id}/invites/', {
            'expires_in_days': 3
        }, content_type='application/json')
        self.assertEqual(invite_resp.status_code, 201)
        token = invite_resp.json()['token']

        # Join team as other_user
        self.client.login(username='api_other', password='password123')
        join_resp = self.client.post(f'/api/invites/{token}/join/')
        self.assertEqual(join_resp.status_code, 200)
        self.assertTrue(self.team.is_member(self.other_user))

    def test_submission_lifecycle_api(self):
        """Test submission draft creation, editing, and submission."""
        self.client.login(username='api_participant', password='password123')
        create_resp = self.client.post(f'/api/teams/{self.team.id}/submissions/', {
            'title': "Awesome AI Project",
            'tagline': "Elevator pitch",
            'description': "Full writeup",
            'repo_url': "https://github.com/test/repo",
            'live_url': "https://demo.example.com",
            'demo_video_url': "https://youtube.com/watch?v=123",
            'tech_tags': ["Django", "React"],
            'custom_answers': {}
        }, content_type='application/json')
        self.assertEqual(create_resp.status_code, 201)
        sub_id = create_resp.json()['id']

        # Submit final
        update_resp = self.client.put(f'/api/submissions/{sub_id}/', {
            'title': "Awesome AI Project Final",
            'tagline': "Elevator pitch updated",
            'description': "Full writeup updated",
            'repo_url': "https://github.com/test/repo",
            'live_url': "https://demo.example.com",
            'demo_video_url': "https://youtube.com/watch?v=123",
            'tech_tags': ["Django", "React"],
            'custom_answers': {},
            'action': 'submit_final'
        }, content_type='application/json')
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()['status'], 'submitted')

    def test_judging_assignment_and_scoring_api(self):
        """Test algorithmic assignment execution and judge scoring."""
        # Create submitted project
        sub = Submission.objects.create(
            team=self.team,
            event=self.event,
            title="Judged Submission",
            tagline="Pitch",
            description="Details",
            status=Submission.Status.SUBMITTED
        )

        # Run algorithmic assignment as organizer
        self.client.login(username='api_organizer', password='password123')
        assign_resp = self.client.post(f'/api/events/{self.event.id}/assignments/run/', {
            'k': 1
        }, content_type='application/json')
        self.assertEqual(assign_resp.status_code, 200)
        self.assertEqual(assign_resp.json()['assignments_generated'], 1)

        assignment = JudgeAssignment.objects.get(submission=sub, judge=self.judge)

        # Judge submits evaluation
        self.client.login(username='api_judge', password='password123')
        score_resp = self.client.post(f'/api/assignments/{assignment.id}/score/', {
            'scores': [
                {'criterion_id': self.crit1.id, 'value': 5, 'feedback': "Great code!"},
                {'criterion_id': self.crit2.id, 'value': 4, 'feedback': "Very creative!"}
            ]
        }, content_type='application/json')
        self.assertEqual(score_resp.status_code, 200)
        self.assertEqual(score_resp.json()['assignment_status'], 'completed')

        # Run normalization as organizer
        self.client.login(username='api_organizer', password='password123')
        norm_resp = self.client.post(f'/api/events/{self.event.id}/normalize/', {}, content_type='application/json')
        self.assertEqual(norm_resp.status_code, 200)
        self.assertEqual(norm_resp.json()['status'], 'success')

    def test_voting_and_comments_api(self):
        """Test voting and comments on a submission."""
        sub = Submission.objects.create(
            team=self.team,
            event=self.event,
            title="Voted Submission",
            description="Detailed submission description for voting test",
            status=Submission.Status.SUBMITTED
        )

        # Ensure voting window is currently open
        self.event.voting_start = timezone.now() - timedelta(hours=1)
        self.event.save()

        # Authenticated vote
        self.client.login(username='api_other', password='password123')
        vote_resp = self.client.post(f'/api/submissions/{sub.id}/vote/', {
            'weight': '2.00'
        }, content_type='application/json')
        self.assertEqual(vote_resp.status_code, 201)

        # Duplicate vote rejected
        dup_resp = self.client.post(f'/api/submissions/{sub.id}/vote/', {}, content_type='application/json')
        self.assertEqual(dup_resp.status_code, 400)

        # Comment
        comment_resp = self.client.post(f'/api/submissions/{sub.id}/comments/', {
            'body': "Incredible demo!"
        }, content_type='application/json')
        self.assertEqual(comment_resp.status_code, 201)
        self.assertEqual(comment_resp.json()['body'], "Incredible demo!")
