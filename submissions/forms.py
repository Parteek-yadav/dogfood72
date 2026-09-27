"""
Submission forms for Dogfood 2026.
Dynamically builds fields from organizer-defined CustomQuestion set.
"""

from django import forms
from events.models import Track, CustomQuestion
from .models import Submission, SubmissionImage


class SubmissionForm(forms.ModelForm):
    tech_tags_input = forms.CharField(
        required=False,
        label="Technologies Used",
        help_text="Comma-separated list of technologies (e.g. Python, Django, Tailwind CSS, PostgreSQL)",
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg',
            'placeholder': 'Django, TailwindCSS, HTMX, PostgreSQL'
        })
    )

    class Meta:
        model = Submission
        fields = [
            'title', 'tagline', 'description', 'track',
            'thumbnail', 'repo_url', 'live_url', 'demo_video_url'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'Project Title'}),
            'tagline': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'One sentence pitch'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 6, 'placeholder': 'What it does, how we built it, challenges...'}),
            'track': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'thumbnail': forms.FileInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'repo_url': forms.URLInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'https://github.com/...'}),
            'live_url': forms.URLInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'https://...'}),
            'demo_video_url': forms.URLInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'https://youtube.com/...'}),
        }

    def __init__(self, *args, event=None, **kwargs):
        self.event = event or (kwargs.get('instance').event if kwargs.get('instance') else None)
        super().__init__(*args, **kwargs)

        # Filter track choices to this event
        if self.event:
            self.fields['track'].queryset = Track.objects.filter(event=self.event)
            self.fields['track'].required = False

        # Populate initial tech tags
        if self.instance and self.instance.pk and self.instance.tech_tags:
            self.fields['tech_tags_input'].initial = ", ".join(self.instance.tech_tags)

        # Dynamically inject form fields for CustomQuestions
        if self.event:
            existing_answers = self.instance.custom_answers if (self.instance and self.instance.pk) else {}
            for q in self.event.custom_questions.all():
                field_name = f"custom_q_{q.id}"
                initial_val = existing_answers.get(str(q.id))
                field_label = f"{q.label}{' *' if q.required else ''}"

                if q.field_type == CustomQuestion.FieldType.TEXT:
                    self.fields[field_name] = forms.CharField(
                        label=field_label,
                        required=False,
                        initial=initial_val,
                        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'})
                    )
                elif q.field_type == CustomQuestion.FieldType.TEXTAREA:
                    self.fields[field_name] = forms.CharField(
                        label=field_label,
                        required=False,
                        initial=initial_val,
                        widget=forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 3})
                    )
                elif q.field_type == CustomQuestion.FieldType.URL:
                    self.fields[field_name] = forms.URLField(
                        label=field_label,
                        required=False,
                        initial=initial_val,
                        widget=forms.URLInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'https://'})
                    )
                elif q.field_type == CustomQuestion.FieldType.SELECT:
                    choices = [('', '-- Select an option --')] + [(c, c) for c in (q.choices or [])]
                    self.fields[field_name] = forms.ChoiceField(
                        label=field_label,
                        required=False,
                        initial=initial_val,
                        choices=choices,
                        widget=forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'})
                    )
                elif q.field_type == CustomQuestion.FieldType.CHECKBOX:
                    self.fields[field_name] = forms.BooleanField(
                        label=field_label,
                        required=False,
                        initial=bool(initial_val),
                        widget=forms.CheckboxInput(attrs={'class': 'h-5 w-5 text-indigo-600 rounded'})
                    )

    def clean(self):
        cleaned_data = super().clean()
        tags_raw = cleaned_data.get('tech_tags_input', '')
        cleaned_data['parsed_tech_tags'] = [t.strip() for t in tags_raw.split(',') if t.strip()]

        # Assemble custom answers
        custom_answers = {}
        if self.event:
            for q in self.event.custom_questions.all():
                field_name = f"custom_q_{q.id}"
                val = cleaned_data.get(field_name)
                if val is not None and val != "":
                    custom_answers[str(q.id)] = val
        cleaned_data['parsed_custom_answers'] = custom_answers
        return cleaned_data


class SubmissionImageForm(forms.ModelForm):
    class Meta:
        model = SubmissionImage
        fields = ['image', 'caption', 'order']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'caption': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'Optional screenshot description'}),
            'order': forms.NumberInput(attrs={'class': 'w-24 px-4 py-2 border rounded-lg', 'min': 0}),
        }
