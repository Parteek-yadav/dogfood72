from django.contrib import admin
from .models import Event, EventRole, Track, Prize, CustomQuestion


class CustomQuestionInline(admin.TabularInline):
    model = CustomQuestion
    extra = 1
    fields = ('order', 'label', 'field_type', 'required', 'choices')


class TrackInline(admin.TabularInline):
    model = Track
    extra = 1


class PrizeInline(admin.TabularInline):
    model = Prize
    extra = 1
    fields = ('rank', 'name', 'amount', 'track')


class EventRoleInline(admin.TabularInline):
    model = EventRole
    extra = 1
    autocomplete_fields = ['user']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'organizer',
        'start_date',
        'end_date',
        'submission_deadline',
        'is_published'
    )
    list_filter = ('is_published', 'start_date', 'submission_deadline')
    search_fields = ('name', 'description', 'organizer__username')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CustomQuestionInline, TrackInline, PrizeInline, EventRoleInline]


@admin.register(EventRole)
class EventRoleAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'role', 'assigned_at')
    list_filter = ('role', 'event')
    search_fields = ('user__username', 'event__name')
    autocomplete_fields = ['user', 'event']


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'event')
    list_filter = ('event',)
    search_fields = ('name', 'event__name')


@admin.register(Prize)
class PrizeAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'track', 'amount', 'rank')
    list_filter = ('event', 'rank')
    search_fields = ('name', 'event__name')


@admin.register(CustomQuestion)
class CustomQuestionAdmin(admin.ModelAdmin):
    list_display = ('label', 'event', 'field_type', 'required', 'order')
    list_filter = ('event', 'field_type', 'required')
    search_fields = ('label', 'event__name')
