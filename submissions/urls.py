from django.urls import path
from . import views

app_name = 'submissions'

urlpatterns = [
    path('team/<int:team_id>/new/', views.submission_create, name='submission_create'),
    path('<int:pk>/edit/', views.submission_edit, name='submission_edit'),
    path('<int:pk>/', views.submission_detail, name='submission_detail'),
    path('<int:pk>/gallery/upload/', views.submission_image_upload, name='submission_image_upload'),
    path('<int:pk>/gallery/<int:image_id>/delete/', views.submission_image_delete, name='submission_image_delete'),
    path('events/<slug:slug>/gallery/', views.public_gallery, name='public_gallery'),
]
