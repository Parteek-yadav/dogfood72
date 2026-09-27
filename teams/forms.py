"""
Team forms for Dogfood 2026.
"""

from django import forms
from .models import Team, Invite


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500',
                'placeholder': 'Team Name (e.g. Quantum Builders)'
            }),
        }


class InviteForm(forms.Form):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg',
            'placeholder': 'Optional: restrict to email (e.g. teammate@example.com)'
        }),
        help_text="Leave blank to create a generic public invite link."
    )
    expires_in_days = forms.IntegerField(
        initial=7,
        min_value=1,
        max_value=30,
        widget=forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
        help_text="Validity period in days (1–30)."
    )
