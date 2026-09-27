"""
Comprehensive tests for Dogfood 2026 T1 milestones:
1. Role enforcement (organizer vs judge vs participant)
2. Submission deadline enforcement (model + view layer + audit log)
3. Team formation & invite token expiry/reuse/duplicate-team prevention
4. CustomQuestion validation (required fields, select choice constraints)
5. Public gallery filtering and publication visibility
"""

from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied

from core.models import AuditLogEntry
from core.permissions import is_event_organizer, is_event_judge, is_team_member
from events.models import Event, EventRole, Track, CustomQuestion
from teams.models import Team, TeamMembership, Invite
from submissions.models import Submission, SubmissionVersion


class RoleEnforcementTests(TestCase):
    """Ensure organizers, judges, and participants cannot breach unauthorized views."""

    def setUp(self):
        self.organizer = User.objects.create_user(username='org_user', password='password123')
        self.judge = User.objects.create_user(username='judge_user', password='password123')
        self.participant = User.objects.create_user(username='hacker_user', password='password123')
        self.visitor = Client()

        now = timezone.now()
        self.event = Event.objects.create(
            name="AI Dogfood Hackathon",
            slug="ai-dogfood-hackathon",
            description="Testing hackathon",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=3),
            submission_deadline=now + timedelta(days=2),
            voting_start=now + timedelta(days=2),
            voting_end=now + timedelta(days=3),
            is_published=True,
            organizer=self.organizer
        )
        EventRole.objects.create(event=self.event, user=self.organizer, role=EventRole.Role.ORGANIZER)
        EventRole.objects.create(event=self.event, user=self.judge, role=EventRole.Role.JUDGE)
        EventRole.objects.create(event=self.event, user=self.participant, role=EventRole.Role.PARTICIPANT)

    def test_permission_helpers(self):
        """Verify core permission helper functions."""
        self.assertTrue(is_event_organizer(self.event, self.organizer))
        self.assertFalse(is_event_organizer(self.event, self.judge))
        self.assertFalse(is_event_organizer(self.event, self.participant))

        self.assertTrue(is_event_judge(self.event, self.judge))
        self.assertFalse(is_event_judge(self.event, self.organizer))
        self.assertFalse(is_event_judge(self.event, self.participant))

    def test_organizer_can_access_management_view(self):
        """Organizer gets HTTP 200 on event management dashboard."""
        client = Client()
        client.login(username='org_user', password='password123')
        url = reverse('events:event_manage', kwargs={'slug': self.event.slug})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_judge_cannot_access_organizer_management_view(self):
        """Judge gets HTTP 403 Forbidden attempting to access organizer management."""
        client = Client()
        client.login(username='judge_user', password='password123')
        url = reverse('events:event_manage', kwargs={'slug': self.event.slug})
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_access_organizer_management_view(self):
        """Participant gets HTTP 403 Forbidden attempting to access organizer management."""
        client = Client()
        client.login(username='hacker_user', password='password123')
        url = reverse('events:event_manage', kwargs={'slug': self.event.slug})
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_visitor_redirected_to_login(self):
        """Anonymous visitor attempting to create event is redirected to login."""
        response = self.visitor.get(reverse('events:event_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)


class TeamInviteTests(TestCase):
    """Validate team formation, token expiration, reuse prevention, and single-team-per-event rules."""

    def setUp(self):
        self.leader = User.objects.create_user(username='leader_bob', password='password123')
        self.teammate = User.objects.create_user(username='teammate_alice', password='password123', email='alice@example.com')
        self.other_user = User.objects.create_user(username='other_charlie', password='password123')

        now = timezone.now()
        self.event = Event.objects.create(
            name="Team Challenge",
            slug="team-challenge",
            description="Event for team testing",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=3),
            submission_deadline=now + timedelta(days=2),
            voting_start=now + timedelta(days=2),
            voting_end=now + timedelta(days=3),
            is_published=True,
            organizer=self.leader
        )

        self.team = Team.objects.create(
            event=self.event,
            name="Quantum Builders",
            created_by=self.leader
        )
        TeamMembership.objects.create(team=self.team, user=self.leader, role=TeamMembership.Role.LEADER)

    def test_valid_token_join_succeeds(self):
        """Joining team via active token creates membership and invalidates token."""
        invite = Invite.objects.create(
            team=self.team,
            created_by=self.leader,
            expires_at=timezone.now() + timedelta(days=3)
        )

        client = Client()
        client.login(username='teammate_alice', password='password123')
        url = reverse('teams:team_join', kwargs={'token': invite.token})

        # POST confirmation
        response = client.post(url)
        self.assertEqual(response.status_code, 302)

        # Verify membership created
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.teammate).exists())

        # Verify invite marked as used
        invite.refresh_from_db()
        self.assertIsNotNone(invite.used_at)
        self.assertFalse(invite.is_valid())

        # Verify audit log recorded
        self.assertTrue(AuditLogEntry.objects.filter(action='team.joined', target_id=str(self.team.id)).exists())

    def test_reused_token_rejected(self):
        """Attempting to use an already used invite token fails."""
        invite = Invite.objects.create(
            team=self.team,
            created_by=self.leader,
            expires_at=timezone.now() + timedelta(days=3),
            used_at=timezone.now() - timedelta(hours=1)
        )

        client = Client()
        client.login(username='other_charlie', password='password123')
        url = reverse('teams:team_join', kwargs={'token': invite.token})
        response = client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already been used")
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.other_user).exists())

    def test_expired_token_rejected(self):
        """Attempting to use an expired invite token fails."""
        invite = Invite.objects.create(
            team=self.team,
            created_by=self.leader,
            expires_at=timezone.now() - timedelta(minutes=10)
        )

        client = Client()
        client.login(username='other_charlie', password='password123')
        url = reverse('teams:team_join', kwargs={'token': invite.token})
        response = client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "has expired")
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.other_user).exists())

    def test_cannot_join_multiple_teams_in_same_event(self):
        """A user cannot join a second team in the same event."""
        # Put charlie on team 2
        team2 = Team.objects.create(event=self.event, name="Alpha Team", created_by=self.other_user)
        TeamMembership.objects.create(team=team2, user=self.other_user, role=TeamMembership.Role.LEADER)

        # Charlie tries to join team 1 via invite
        invite = Invite.objects.create(
            team=self.team,
            created_by=self.leader,
            expires_at=timezone.now() + timedelta(days=3)
        )

        client = Client()
        client.login(username='other_charlie', password='password123')
        url = reverse('teams:team_join', kwargs={'token': invite.token})
        response = client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already a member of team")
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.other_user).exists())


class CustomQuestionValidationTests(TestCase):
    """Validate dynamic form validation: required fields, types, and select choices."""

    def setUp(self):
        self.user = User.objects.create_user(username='sub_user', password='password123')
        now = timezone.now()
        self.event = Event.objects.create(
            name="Question Testing Event",
            slug="question-testing-event",
            description="Event with custom questions",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=3),
            submission_deadline=now + timedelta(days=2),
            voting_start=now + timedelta(days=2),
            voting_end=now + timedelta(days=3),
            is_published=True,
            organizer=self.user
        )

        self.q_required = CustomQuestion.objects.create(
            event=self.event,
            label="What inspired your project?",
            field_type=CustomQuestion.FieldType.TEXT,
            required=True,
            order=1
        )
        self.q_select = CustomQuestion.objects.create(
            event=self.event,
            label="Primary Deployment Architecture",
            field_type=CustomQuestion.FieldType.SELECT,
            required=False,
            choices=["Serverless", "Containers", "Bare Metal"],
            order=2
        )

        self.team = Team.objects.create(event=self.event, name="Rocket Builders", created_by=self.user)
        TeamMembership.objects.create(team=self.team, user=self.user, role=TeamMembership.Role.LEADER)

    def test_missing_required_question_on_submit_raises_validation_error(self):
        """A submission marked 'submitted' without answering a required question is rejected."""
        sub = Submission(
            team=self.team,
            event=self.event,
            title="Rocket Flight",
            description="Testing submission",
            status=Submission.Status.SUBMITTED,
            custom_answers={}  # Missing q_required!
        )
        with self.assertRaises(ValidationError) as ctx:
            sub.full_clean()
        self.assertIn('custom_answers', ctx.exception.message_dict)

    def test_answering_required_question_on_submit_succeeds(self):
        """Supplying the required answer allows submission to pass clean and save."""
        sub = Submission(
            team=self.team,
            event=self.event,
            title="Rocket Flight",
            description="Testing submission",
            status=Submission.Status.SUBMITTED,
            custom_answers={str(self.q_required.id): "A childhood dream of rockets."}
        )
        sub.full_clean()
        sub.save()
        self.assertEqual(sub.status, Submission.Status.SUBMITTED)
        self.assertIsNotNone(sub.submitted_at)

    def test_invalid_select_choice_rejected(self):
        """Submitting a choice not defined in choices list is rejected."""
        sub = Submission(
            team=self.team,
            event=self.event,
            title="Rocket Flight",
            description="Testing submission",
            status=Submission.Status.DRAFT,
            custom_answers={
                str(self.q_required.id): "Valid text",
                str(self.q_select.id): "Monolithic On-Premises (Invalid)"
            }
        )
        with self.assertRaises(ValidationError):
            sub.full_clean()


class DeadlineEnforcementTests(TestCase):
    """Verify that no edits are allowed after submission_deadline has passed."""

    def setUp(self):
        self.user = User.objects.create_user(username='deadline_dev', password='password123')
        now = timezone.now()

        # Event with deadline already passed 1 hour ago
        self.event = Event.objects.create(
            name="Past Event",
            slug="past-event",
            description="Deadline passed event",
            start_date=now - timedelta(days=3),
            end_date=now + timedelta(days=1),
            submission_deadline=now - timedelta(hours=1),
            voting_start=now - timedelta(hours=1),
            voting_end=now + timedelta(days=1),
            is_published=True,
            organizer=self.user
        )

        self.team = Team.objects.create(event=self.event, name="Late Team", created_by=self.user)
        TeamMembership.objects.create(team=self.team, user=self.user, role=TeamMembership.Role.LEADER)

        # Create submission directly in db
        self.submission = Submission.objects.create(
            team=self.team,
            event=self.event,
            title="Initial Title",
            description="Initial Description",
            status=Submission.Status.DRAFT
        )

    def test_post_edit_after_deadline_is_rejected_and_audit_logged(self):
        """POST request to edit a submission after deadline is rejected (403) and logged."""
        client = Client()
        client.login(username='deadline_dev', password='password123')

        url = reverse('submissions:submission_edit', kwargs={'pk': self.submission.pk})
        response = client.post(url, {
            'title': 'Hacked After Deadline',
            'description': 'Trying to bypass deadline',
            'action': 'save_draft'
        })

        # View rejects with 403 Forbidden
        self.assertEqual(response.status_code, 403)

        # Ensure title in DB did not change
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.title, "Initial Title")

        # Verify audit log entry exists
        audit_entry = AuditLogEntry.objects.filter(
            action='submission.deadline_blocked_edit_attempt',
            target_id=str(self.submission.pk)
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.actor, self.user)

    def test_model_clean_rejects_edits_after_deadline(self):
        """Model-layer clean() check blocks edits after deadline."""
        self.submission.title = "Direct Model Modification"
        with self.assertRaises(ValidationError) as ctx:
            self.submission.clean()
        self.assertIn("submission deadline for this event has passed", str(ctx.exception))


class PublicGalleryTests(TestCase):
    """Verify public gallery only displays submitted projects for published events."""

    def setUp(self):
        self.user = User.objects.create_user(username='gallery_user', password='password123')
        now = timezone.now()

        self.published_event = Event.objects.create(
            name="Open Hackathon",
            slug="open-hackathon",
            description="Published event",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=2),
            submission_deadline=now + timedelta(days=1),
            voting_start=now + timedelta(days=1),
            voting_end=now + timedelta(days=2),
            is_published=True,
            organizer=self.user
        )

        self.track_ai = Track.objects.create(event=self.published_event, name="AI Track")
        self.track_web = Track.objects.create(event=self.published_event, name="Web3 Track")

        team_a = Team.objects.create(event=self.published_event, name="Team A", created_by=self.user)
        team_b = Team.objects.create(event=self.published_event, name="Team B", created_by=self.user)

        # Submitted project in AI Track
        self.sub_submitted = Submission.objects.create(
            team=team_a,
            event=self.published_event,
            track=self.track_ai,
            title="Super AI Bot",
            tagline="An intelligent agent",
            description="Does smart things",
            tech_tags=["Python", "PyTorch"],
            status=Submission.Status.SUBMITTED
        )

        # Draft project in Web3 Track
        self.sub_draft = Submission.objects.create(
            team=team_b,
            event=self.published_event,
            track=self.track_web,
            title="Unfinished Blockchain App",
            description="Work in progress",
            status=Submission.Status.DRAFT
        )

    def test_only_submitted_projects_appear_in_gallery(self):
        """Draft projects must not appear in the public gallery."""
        client = Client()
        url = reverse('submissions:public_gallery', kwargs={'slug': self.published_event.slug})
        response = client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Super AI Bot")
        self.assertNotContains(response, "Unfinished Blockchain App")

    def test_track_filtering(self):
        """Filtering by track ID narrows down the gallery results."""
        client = Client()
        url = reverse('submissions:public_gallery', kwargs={'slug': self.published_event.slug})

        # Filter by AI Track -> 1 result
        res_ai = client.get(f"{url}?track={self.track_ai.id}")
        self.assertContains(res_ai, "Super AI Bot")

        # Filter by Web3 Track -> 0 results (since web3 project is a draft)
        res_web = client.get(f"{url}?track={self.track_web.id}")
        self.assertNotContains(res_web, "Super AI Bot")
        self.assertContains(res_web, "No submitted projects found")

    def test_search_filtering(self):
        """Searching by tech tag finds matching submitted project."""
        client = Client()
        url = reverse('submissions:public_gallery', kwargs={'slug': self.published_event.slug})

        # Search PyTorch
        res_search = client.get(f"{url}?q=PyTorch")
        self.assertContains(res_search, "Super AI Bot")

        # Search NonExistent
        res_none = client.get(f"{url}?q=NonExistentTechnology")
        self.assertNotContains(res_none, "Super AI Bot")
