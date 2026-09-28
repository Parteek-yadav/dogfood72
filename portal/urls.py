"""
URL configuration for Dogfood 2026 portal project.
Provides web UI routes, acceptance checker routes, and complete DRF API endpoints.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from drf_spectacular.utils import extend_schema

from events import api as events_api
from teams import api as teams_api
from submissions import views as submissions_views
from submissions import api as submissions_api
from judging import api as judging_api
from voting import api as voting_api


# Hidden alias view to support trailing slash without schema collision
@extend_schema(exclude=True)
class JudgeScoresSlashAPIView(judging_api.JudgeScoresAPIView):
    pass


urlpatterns = [
    path('admin/', admin.site.urls),

    # =========================================================================
    # Acceptance Checker Dedicated Routes
    # =========================================================================
    path('projects', submissions_views.projects_list, name='checker_projects'),
    path('projects/', submissions_views.projects_list, name='checker_projects_slash'),
    path('projects/new', submissions_views.projects_new, name='checker_projects_new'),
    path('projects/new/', submissions_views.projects_new, name='checker_projects_new_slash'),
    path('api/judge/scores', judging_api.JudgeScoresAPIView.as_view(), name='api_judge_scores'),
    path('api/judge/scores/', JudgeScoresSlashAPIView.as_view(), name='api_judge_scores_slash'),
    path('api/export.csv', judging_api.ExportCSVAPIView.as_view(), name='api_export_csv'),

    # =========================================================================
    # Web UI Applications (Template Views)
    # =========================================================================
    path('auth/', include('accounts.urls', namespace='accounts')),
    path('teams/', include('teams.urls', namespace='teams')),
    path('submissions/', include('submissions.urls', namespace='submissions')),
    path('judging/', include('judging.urls', namespace='judging')),
    path('', include('events.urls', namespace='events')),

    # =========================================================================
    # REST API: Events & Sub-Resources
    # =========================================================================
    path('api/events/', events_api.EventListCreateAPIView.as_view(), name='api_event_list_create'),
    path('api/events/<int:pk>/', events_api.EventDetailAPIView.as_view(), name='api_event_detail'),
    path('api/events/<int:event_id>/tracks/', events_api.TrackListCreateAPIView.as_view(), name='api_event_tracks'),
    path('api/events/<int:event_id>/tracks/<int:pk>/', events_api.TrackDetailAPIView.as_view(), name='api_event_track_detail'),
    path('api/events/<int:event_id>/prizes/', events_api.PrizeListCreateAPIView.as_view(), name='api_event_prizes'),
    path('api/events/<int:event_id>/prizes/<int:pk>/', events_api.PrizeDetailAPIView.as_view(), name='api_event_prize_detail'),
    path('api/events/<int:event_id>/questions/', events_api.CustomQuestionListCreateAPIView.as_view(), name='api_event_questions'),
    path('api/events/<int:event_id>/questions/<int:pk>/', events_api.CustomQuestionDetailAPIView.as_view(), name='api_event_question_detail'),
    path('api/events/<int:event_id>/roles/', events_api.EventRoleListCreateAPIView.as_view(), name='api_event_roles'),

    # =========================================================================
    # REST API: Teams & Invites
    # =========================================================================
    path('api/events/<int:event_id>/teams/', teams_api.EventTeamListCreateAPIView.as_view(), name='api_event_teams'),
    path('api/teams/<int:pk>/', teams_api.TeamDetailAPIView.as_view(), name='api_team_detail'),
    path('api/teams/<int:pk>/invites/', teams_api.TeamInviteCreateAPIView.as_view(), name='api_team_invites'),
    path('api/invites/<str:token>/join/', teams_api.TeamJoinAPIView.as_view(), name='api_invite_join'),
    path('api/teams/<int:pk>/members/<int:user_id>/', teams_api.TeamMemberRemoveAPIView.as_view(), name='api_team_member_remove'),

    # =========================================================================
    # REST API: Submissions & Gallery
    # =========================================================================
    path('api/events/<int:event_id>/submissions/', submissions_api.EventSubmissionListAPIView.as_view(), name='api_event_submissions'),
    path('api/teams/<int:team_id>/submissions/', submissions_api.TeamSubmissionCreateAPIView.as_view(), name='api_team_submissions'),
    path('api/submissions/<int:pk>/', submissions_api.SubmissionDetailUpdateAPIView.as_view(), name='api_submission_detail'),
    path('api/submissions/<int:pk>/gallery/', submissions_api.SubmissionImageUploadAPIView.as_view(), name='api_submission_gallery'),
    path('api/submissions/<int:pk>/gallery/<int:image_id>/', submissions_api.SubmissionImageDeleteAPIView.as_view(), name='api_submission_gallery_delete'),

    # =========================================================================
    # REST API: Judging, Assignments, Scoring, Normalization & Exports
    # =========================================================================
    path('api/events/<int:event_id>/rubric/', judging_api.RubricManageAPIView.as_view(), name='api_rubric_manage'),
    path('api/events/<int:event_id>/rubric/criteria/', judging_api.RubricCriterionListCreateAPIView.as_view(), name='api_rubric_criteria'),
    path('api/events/<int:event_id>/rubric/criteria/<int:pk>/', judging_api.RubricCriterionDetailAPIView.as_view(), name='api_rubric_criterion_detail'),
    path('api/events/<int:event_id>/assignments/run/', judging_api.RunAlgorithmicAssignmentsAPIView.as_view(), name='api_run_assignments'),
    path('api/events/<int:event_id>/assignments/override/', judging_api.ManualAssignmentOverrideAPIView.as_view(), name='api_assignment_override'),
    path('api/assignments/<int:assignment_id>/score/', judging_api.ScoreSubmissionAPIView.as_view(), name='api_score_submission'),
    path('api/events/<int:event_id>/normalize/', judging_api.TriggerNormalizationAPIView.as_view(), name='api_trigger_normalization'),
    path('api/events/<int:event_id>/my-assignments/', judging_api.MyAssignmentsAPIView.as_view(), name='api_my_assignments'),
    path('api/submissions/<int:submission_id>/scores/', judging_api.SubmissionScoresAPIView.as_view(), name='api_submission_scores'),
    path('api/events/<int:event_id>/judge-progress/', judging_api.JudgeProgressAPIView.as_view(), name='api_judge_progress'),
    path('api/events/<int:event_id>/export/normalized/', judging_api.ExportNormalizedCSVAPIView.as_view(), name='api_export_normalized'),
    path('api/events/<int:event_id>/export/assignments/', judging_api.ExportAssignmentsCSVAPIView.as_view(), name='api_export_assignments'),

    # =========================================================================
    # REST API: Voting & Community Comments
    # =========================================================================
    path('api/submissions/<int:pk>/vote/', voting_api.VoteCastAPIView.as_view(), name='api_submission_vote'),
    path('api/submissions/<int:pk>/votes/', voting_api.VoteSummaryAPIView.as_view(), name='api_submission_votes_summary'),
    path('api/submissions/<int:pk>/comments/', voting_api.CommentListCreateAPIView.as_view(), name='api_submission_comments'),

    # =========================================================================
    # OpenAPI Schema & Interactive Docs
    # =========================================================================
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
