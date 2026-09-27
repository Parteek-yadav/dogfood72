from django.urls import path
from . import views
from . import api

app_name = 'judging'

urlpatterns = [
    # Judge Portal
    path('my-assignments/', views.my_assignments, name='my_assignments'),
    path('assignments/<int:assignment_id>/score/', views.score_submission, name='score_submission'),

    # Organizer Rubric & Assignment Operations
    path('events/<int:event_id>/rubric/', views.rubric_manage, name='rubric_manage'),
    path('events/<int:event_id>/assignments/', views.assignment_manage, name='assignment_manage'),
    path('events/<int:event_id>/assignments/run/', views.run_algorithmic_assignments, name='run_algorithmic_assignments'),
    path('events/<int:event_id>/assignments/override/', views.manual_assignment_override, name='manual_assignment_override'),
    path('events/<int:event_id>/progress/', views.judge_progress_dashboard, name='judge_progress_dashboard'),
    path('events/<int:event_id>/normalize/', views.trigger_normalization_view, name='trigger_normalization'),

    # CSV Exports
    path('events/<int:event_id>/export/raw-scores/', views.export_raw_scores_csv, name='export_raw_scores_csv'),
    path('events/<int:event_id>/export/normalized-scores/', views.export_normalized_scores_csv, name='export_normalized_scores_csv'),
    path('events/<int:event_id>/export/assignments/', views.export_judge_assignments_csv, name='export_judge_assignments_csv'),

    # DRF API Endpoints
    path('api/events/<int:event_id>/my-assignments/', api.MyAssignmentsAPIView.as_view(), name='api_my_assignments'),
    path('api/submissions/<int:submission_id>/scores/', api.SubmissionScoresAPIView.as_view(), name='api_submission_scores'),
    path('api/events/<int:event_id>/judge-progress/', api.JudgeProgressAPIView.as_view(), name='api_judge_progress'),
]
