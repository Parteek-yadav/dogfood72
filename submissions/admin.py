from django.contrib import admin
from .models import Submission, SubmissionImage, SubmissionVersion


class SubmissionImageInline(admin.TabularInline):
    model = SubmissionImage
    extra = 1
    fields = ('order', 'image', 'caption')


class SubmissionVersionInline(admin.TabularInline):
    model = SubmissionVersion
    extra = 0
    readonly_fields = ('version_number', 'title', 'tagline', 'status', 'created_at', 'created_by')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('title', 'team', 'event', 'track', 'status', 'submitted_at', 'created_at')
    list_filter = ('status', 'event', 'track')
    search_fields = ('title', 'tagline', 'team__name', 'event__name')
    autocomplete_fields = ['team', 'event', 'track']
    inlines = [SubmissionImageInline, SubmissionVersionInline]
    readonly_fields = ('created_at', 'updated_at', 'submitted_at')


@admin.register(SubmissionImage)
class SubmissionImageAdmin(admin.ModelAdmin):
    list_display = ('submission', 'caption', 'order')
    list_filter = ('submission__event',)
    search_fields = ('submission__title', 'caption')
    autocomplete_fields = ['submission']


@admin.register(SubmissionVersion)
class SubmissionVersionAdmin(admin.ModelAdmin):
    list_display = ('submission', 'version_number', 'status', 'created_at', 'created_by')
    list_filter = ('status', 'submission__event')
    search_fields = ('submission__title', 'title')
    readonly_fields = ('submission', 'version_number', 'title', 'tagline', 'description', 'custom_answers', 'status', 'created_at', 'created_by')
