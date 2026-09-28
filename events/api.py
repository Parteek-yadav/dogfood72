"""
DRF API views for Event CRUD, Tracks, Prizes, Custom Questions, and Event Roles.
"""

from rest_framework import generics, permissions, status, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.models import AuditLogEntry
from core.permissions import is_event_organizer
from .models import Event, EventRole, Track, Prize, CustomQuestion
from .serializers import (
    EventListSerializer,
    EventDetailSerializer,
    EventCreateUpdateSerializer,
    TrackSerializer,
    PrizeSerializer,
    CustomQuestionSerializer,
    EventRoleSerializer,
    EventRoleCreateSerializer,
)


class EventListCreateAPIView(generics.ListCreateAPIView):
    """
    GET /api/events/
    Lists published events (and draft events if the user is an organizer).

    POST /api/events/
    Creates a new hackathon event. Automatically assigns organizer role to current user.
    """
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return EventCreateUpdateSerializer
        return EventListSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return Event.objects.filter(
                Q(is_published=True) |
                Q(organizer=user) |
                Q(roles__user=user, roles__role=EventRole.Role.ORGANIZER)
            ).distinct().order_by('-start_date')
        return Event.objects.filter(is_published=True).order_by('-start_date')

    @extend_schema(
        summary="List hackathon events",
        responses={200: EventListSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a new hackathon event",
        request=EventCreateUpdateSerializer,
        responses={201: EventDetailSerializer}
    )
    def post(self, request, *args, **kwargs):
        serializer = EventCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save(organizer=request.user)

        # Assign organizer role
        EventRole.objects.get_or_create(
            event=event,
            user=request.user,
            role=EventRole.Role.ORGANIZER
        )
        AuditLogEntry.log('event.created', event, actor=request.user)

        return Response(EventDetailSerializer(event).data, status=status.HTTP_201_CREATED)


class EventDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/events/{id}/
    Retrieve event detail with tracks, prizes, and custom questions.

    PUT/PATCH /api/events/{id}/
    Update event schedule and details. Organizer permission required.

    DELETE /api/events/{id}/
    Delete event. Organizer permission required.
    """
    queryset = Event.objects.all()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return EventCreateUpdateSerializer
        return EventDetailSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def check_organizer(self, event):
        if not is_event_organizer(event, self.request.user):
            raise exceptions.PermissionDenied("Organizer permissions required for this event.")

    @extend_schema(
        summary="Retrieve event details",
        responses={200: EventDetailSerializer}
    )
    def get(self, request, *args, **kwargs):
        event = self.get_object()
        if not event.is_published and not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("This event has not been published yet.")
        return Response(EventDetailSerializer(event).data)

    @extend_schema(
        summary="Update event details",
        request=EventCreateUpdateSerializer,
        responses={200: EventDetailSerializer}
    )
    def put(self, request, *args, **kwargs):
        event = self.get_object()
        self.check_organizer(event)
        serializer = EventCreateUpdateSerializer(event, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_event = serializer.save()
        AuditLogEntry.log('event.edited', updated_event, actor=request.user)
        return Response(EventDetailSerializer(updated_event).data)

    @extend_schema(
        summary="Partially update event details",
        request=EventCreateUpdateSerializer,
        responses={200: EventDetailSerializer}
    )
    def patch(self, request, *args, **kwargs):
        event = self.get_object()
        self.check_organizer(event)
        serializer = EventCreateUpdateSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_event = serializer.save()
        AuditLogEntry.log('event.edited', updated_event, actor=request.user)
        return Response(EventDetailSerializer(updated_event).data)

    @extend_schema(
        summary="Delete an event",
        responses={204: None}
    )
    def delete(self, request, *args, **kwargs):
        event = self.get_object()
        self.check_organizer(event)
        AuditLogEntry.log('event.deleted', event, actor=request.user)
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrackListCreateAPIView(APIView):
    """
    GET, POST /api/events/{event_id}/tracks/
    List tracks or add a track to an event (organizer required for POST).
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="List event tracks",
        responses={200: TrackSerializer(many=True)}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        tracks = event.tracks.all()
        return Response(TrackSerializer(tracks, many=True).data)

    @extend_schema(
        summary="Create an event track",
        request=TrackSerializer,
        responses={201: TrackSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        serializer = TrackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        track = serializer.save(event=event)
        return Response(TrackSerializer(track).data, status=status.HTTP_201_CREATED)


class TrackDetailAPIView(APIView):
    """
    DELETE /api/events/{event_id}/tracks/{pk}/
    Delete a track from an event (organizer required).
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete a track",
        responses={204: None}
    )
    def delete(self, request, event_id, pk):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        track = get_object_or_404(Track, pk=pk, event=event)
        track.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrizeListCreateAPIView(APIView):
    """
    GET, POST /api/events/{event_id}/prizes/
    List prizes or add a prize to an event (organizer required for POST).
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="List event prizes",
        responses={200: PrizeSerializer(many=True)}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        prizes = event.prizes.select_related('track').all()
        return Response(PrizeSerializer(prizes, many=True).data)

    @extend_schema(
        summary="Create an event prize",
        request=PrizeSerializer,
        responses={201: PrizeSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        serializer = PrizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prize = serializer.save(event=event)
        return Response(PrizeSerializer(prize).data, status=status.HTTP_201_CREATED)


class PrizeDetailAPIView(APIView):
    """
    DELETE /api/events/{event_id}/prizes/{pk}/
    Delete a prize from an event (organizer required).
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete a prize",
        responses={204: None}
    )
    def delete(self, request, event_id, pk):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        prize = get_object_or_404(Prize, pk=pk, event=event)
        prize.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomQuestionListCreateAPIView(APIView):
    """
    GET, POST /api/events/{event_id}/questions/
    List or add organizer-defined custom questions for submission forms.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @extend_schema(
        summary="List custom questions for an event",
        responses={200: CustomQuestionSerializer(many=True)}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        questions = event.custom_questions.all()
        return Response(CustomQuestionSerializer(questions, many=True).data)

    @extend_schema(
        summary="Add custom question to event submission form",
        request=CustomQuestionSerializer,
        responses={201: CustomQuestionSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        serializer = CustomQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        q = serializer.save(event=event)
        AuditLogEntry.log('event.question_added', q, actor=request.user, metadata={'label': q.label})
        return Response(CustomQuestionSerializer(q).data, status=status.HTTP_201_CREATED)


class CustomQuestionDetailAPIView(APIView):
    """
    DELETE /api/events/{event_id}/questions/{pk}/
    Delete a custom question from an event.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Delete custom question",
        responses={204: None}
    )
    def delete(self, request, event_id, pk):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        q = get_object_or_404(CustomQuestion, pk=pk, event=event)
        label = q.label
        q.delete()
        AuditLogEntry.log('event.question_deleted', event, actor=request.user, metadata={'label': label})
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventRoleListCreateAPIView(APIView):
    """
    GET, POST /api/events/{event_id}/roles/
    List roles or assign a role (organizer, judge, participant) to a user in this event.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List roles assigned in this event",
        responses={200: EventRoleSerializer(many=True)}
    )
    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        roles = event.roles.select_related('user').all()
        return Response(EventRoleSerializer(roles, many=True).data)

    @extend_schema(
        summary="Assign a role to a user for this event",
        request=EventRoleCreateSerializer,
        responses={201: EventRoleSerializer}
    )
    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if not is_event_organizer(event, request.user):
            raise exceptions.PermissionDenied("Organizer permissions required.")
        serializer = EventRoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data['user_id']
        role_val = serializer.validated_data['role']

        from django.contrib.auth.models import User
        target_user = get_object_or_404(User, pk=user_id)

        role_obj, created = EventRole.objects.get_or_create(
            event=event,
            user=target_user,
            role=role_val
        )
        AuditLogEntry.log('event.role_assigned', event, actor=request.user, metadata={'user_id': user_id, 'role': role_val})
        return Response(EventRoleSerializer(role_obj).data, status=status.HTTP_201_CREATED)
