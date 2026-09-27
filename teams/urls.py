from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    path('events/<slug:event_slug>/create/', views.team_create, name='team_create'),
    path('<int:pk>/', views.team_detail, name='team_detail'),
    path('<int:pk>/invites/create/', views.team_invite_create, name='team_invite_create'),
    path('join/<str:token>/', views.team_join, name='team_join'),
]
