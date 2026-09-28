"""
Event management forms for Dogfood 2026.
"""

import json
from django import forms
from .models import Event, Track, Prize, CustomQuestion


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            'name', 'slug', 'description',
            'start_date', 'end_date', 'submission_deadline',
            'voting_start', 'voting_end', 'is_published'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 bg-white text-black font-medium'}),
            'slug': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 bg-white text-black font-medium', 'placeholder': 'unique-event-slug'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 bg-white text-black font-medium', 'rows': 5}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg bg-white text-black font-medium'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg bg-white text-black font-medium'}),
            'submission_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg bg-white text-black font-medium'}),
            'voting_start': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg bg-white text-black font-medium'}),
            'voting_end': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg bg-white text-black font-medium'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'h-5 w-5 text-indigo-600 rounded'}),
        }


class TrackForm(forms.ModelForm):
    class Meta:
        model = Track
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'e.g. Best AI Agent'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 3}),
        }


class PrizeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)
        if event:
            self.fields['track'].queryset = Track.objects.filter(event=event)

    class Meta:
        model = Prize
        fields = ['name', 'amount', 'rank', 'description', 'track']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'amount': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': '$5,000'}),
            'rank': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'min': 1}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 2}),
            'track': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
        }


class CustomQuestionForm(forms.ModelForm):
    choices_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg text-sm',
            'rows': 3,
            'placeholder': 'Option 1\nOption 2\nOption 3 (one per line, for select dropdowns)'
        }),
        help_text="One option per line for 'Select Dropdown' question type."
    )

    class Meta:
        model = CustomQuestion
        fields = ['label', 'field_type', 'required', 'order']
        widgets = {
            'label': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'Question prompt'}),
            'field_type': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'required': forms.CheckboxInput(attrs={'class': 'h-5 w-5 text-indigo-600 rounded'}),
            'order': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'min': 0}),
        }

    def clean(self):
        cleaned_data = super().clean()
        field_type = cleaned_data.get('field_type')
        choices_text = cleaned_data.get('choices_text', '')

        if field_type == CustomQuestion.FieldType.SELECT:
            lines = [line.strip() for line in choices_text.splitlines() if line.strip()]
            if not lines:
                self.add_error('choices_text', "Select fields require at least one choice.")
            cleaned_data['parsed_choices'] = lines
        else:
            cleaned_data['parsed_choices'] = []
        return cleaned_data
