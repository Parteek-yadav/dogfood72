from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('new/', views.event_create, name='event_create'),
    path('<slug:slug>/', views.event_detail, name='event_detail'),
    path('<slug:slug>/edit/', views.event_edit, name='event_edit'),
    path('<slug:slug>/manage/', views.event_manage, name='event_manage'),

    # Custom Questions
    path('<slug:slug>/questions/add/', views.event_question_add, name='event_question_add'),
    path('<slug:slug>/questions/<int:question_id>/delete/', views.event_question_delete, name='event_question_delete'),
    path('<slug:slug>/questions/reorder/', views.event_question_reorder, name='event_question_reorder'),

    # Tracks
    path('<slug:slug>/tracks/add/', views.event_track_add, name='event_track_add'),
    path('<slug:slug>/tracks/<int:track_id>/delete/', views.event_track_delete, name='event_track_delete'),

    # Prizes
    path('<slug:slug>/prizes/add/', views.event_prize_add, name='event_prize_add'),
    path('<slug:slug>/prizes/<int:prize_id>/delete/', views.event_prize_delete, name='event_prize_delete'),
]
