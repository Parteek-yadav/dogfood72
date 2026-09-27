"""
Judging forms for Dogfood 2026.
"""

from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from .models import Rubric, RubricCriterion, Score, JudgeAssignment


class RubricForm(forms.ModelForm):
    class Meta:
        model = Rubric
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'placeholder': 'Rubric Name'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 3, 'placeholder': 'Judging instructions...'}),
        }


class RubricCriterionForm(forms.ModelForm):
    class Meta:
        model = RubricCriterion
        fields = ['name', 'description', 'weight', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-1.5 border rounded-lg text-sm', 'placeholder': 'Criterion Name'}),
            'description': forms.TextInput(attrs={'class': 'w-full px-3 py-1.5 border rounded-lg text-sm', 'placeholder': 'Guide'}),
            'weight': forms.NumberInput(attrs={'class': 'w-24 px-3 py-1.5 border rounded-lg text-sm', 'step': '0.01'}),
            'order': forms.NumberInput(attrs={'class': 'w-16 px-3 py-1.5 border rounded-lg text-sm', 'min': 0}),
        }


RubricCriterionFormSet = inlineformset_factory(
    Rubric,
    RubricCriterion,
    form=RubricCriterionForm,
    extra=3,
    can_delete=True
)


class JudgeAssignmentForm(forms.ModelForm):
    class Meta:
        model = JudgeAssignment
        fields = ['judge', 'submission']
        widgets = {
            'judge': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg'}),
            'submission': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg'}),
        }


class ScoreInputForm(forms.Form):
    """Dynamically handles 1-5 rating and optional feedback for a RubricCriterion."""
    def __init__(self, *args, criteria=None, initial_scores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.criteria = criteria or []
        initial_scores = initial_scores or {}

        for crit in self.criteria:
            field_name = f"criterion_{crit.id}"
            comment_name = f"feedback_{crit.id}"

            existing_val = initial_scores.get(crit.id, {}).get('value')
            existing_fb = initial_scores.get(crit.id, {}).get('feedback', '')

            self.fields[field_name] = forms.IntegerField(
                min_value=1,
                max_value=5,
                initial=existing_val,
                required=False,
                label=crit.name,
                help_text=f"Weight: {crit.weight}% &bull; {crit.description}",
                widget=forms.RadioSelect(
                    choices=[(i, str(i)) for i in range(1, 6)],
                    attrs={'class': 'flex space-x-4 items-center'}
                )
            )
            self.fields[comment_name] = forms.CharField(
                required=False,
                initial=existing_fb,
                widget=forms.TextInput(attrs={
                    'class': 'w-full px-3 py-1.5 border rounded-lg text-xs mt-1',
                    'placeholder': 'Optional feedback notes for this criterion...'
                })
            )
