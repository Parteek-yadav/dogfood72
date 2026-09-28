"""
URL configuration for Dogfood 2026 portal project.
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

from judging import api as judging_api
from submissions import views as submissions_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Acceptance Checker Routes
    path('projects', submissions_views.projects_list, name='checker_projects'),
    path('projects/', submissions_views.projects_list, name='checker_projects_slash'),
    path('projects/new', submissions_views.projects_new, name='checker_projects_new'),
    path('projects/new/', submissions_views.projects_new, name='checker_projects_new_slash'),
    path('api/judge/scores', judging_api.JudgeScoresAPIView.as_view(), name='api_judge_scores'),
    path('api/judge/scores/', judging_api.JudgeScoresAPIView.as_view(), name='api_judge_scores_slash'),
    path('api/export.csv', judging_api.ExportCSVAPIView.as_view(), name='api_export_csv'),

    # Web Applications
    path('auth/', include('accounts.urls', namespace='accounts')),
    path('teams/', include('teams.urls', namespace='teams')),
    path('submissions/', include('submissions.urls', namespace='submissions')),
    path('judging/', include('judging.urls', namespace='judging')),
    path('', include('events.urls', namespace='events')),

    # Spec-Specific Judging API Routes
    path('api/events/<int:event_id>/my-assignments/', judging_api.MyAssignmentsAPIView.as_view(), name='api_my_assignments'),
    path('api/submissions/<int:submission_id>/scores/', judging_api.SubmissionScoresAPIView.as_view(), name='api_submission_scores'),
    path('api/events/<int:event_id>/judge-progress/', judging_api.JudgeProgressAPIView.as_view(), name='api_judge_progress'),

    # OpenAPI Schema & Interactive Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
