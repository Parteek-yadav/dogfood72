from django.contrib import admin
from .models import Rubric, RubricCriterion, JudgeAssignment, Score, NormalizedScore


class RubricCriterionInline(admin.TabularInline):
    model = RubricCriterion
    extra = 3
    fields = ('order', 'name', 'weight', 'description')


class ScoreInline(admin.TabularInline):
    model = Score
    extra = 0
    fields = ('criterion', 'value', 'feedback')


@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'total_weight', 'created_at')
    list_filter = ('event',)
    search_fields = ('name', 'event__name')
    inlines = [RubricCriterionInline]


@admin.register(RubricCriterion)
class RubricCriterionAdmin(admin.ModelAdmin):
    list_display = ('name', 'rubric', 'weight', 'order')
    list_filter = ('rubric__event', 'rubric')
    search_fields = ('name', 'rubric__name')


@admin.register(JudgeAssignment)
class JudgeAssignmentAdmin(admin.ModelAdmin):
    list_display = ('event', 'judge', 'submission', 'status', 'assigned_at', 'completed_at')
    list_filter = ('status', 'event')
    search_fields = ('judge__username', 'submission__title', 'event__name')
    autocomplete_fields = ['judge', 'submission', 'event']
    inlines = [ScoreInline]


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'criterion', 'value', 'created_at')
    list_filter = ('value', 'assignment__event')
    search_fields = ('assignment__judge__username', 'assignment__submission__title', 'criterion__name')
    autocomplete_fields = ['assignment', 'criterion']


@admin.register(NormalizedScore)
class NormalizedScoreAdmin(admin.ModelAdmin):
    list_display = ('submission', 'method', 'raw_mean', 'normalized_value', 'computed_at')
    list_filter = ('method', 'submission__event')
    search_fields = ('submission__title', 'submission__event__name')
    readonly_fields = ('computed_at',)
