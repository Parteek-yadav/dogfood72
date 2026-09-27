"""
Authentication views for Dogfood 2026.
Self-contained session-based auth supporting both htmx and standard POST forms.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .forms import SignupForm, LoginForm


def signup_view(request):
    """Register a new participant or platform user."""
    if request.user.is_authenticated:
        return redirect('events:event_list')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            auth_login(request, user)
            messages.success(request, f"Welcome to Dogfood 2026, @{user.username}!")
            return redirect('events:event_list')
    else:
        form = SignupForm()

    return render(request, 'accounts/signup.html', {'form': form})


def login_view(request):
    """Authenticate and create session for a user."""
    if request.user.is_authenticated:
        return redirect('events:event_list')

    next_url = request.GET.get('next') or request.POST.get('next') or 'events:event_list'

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, f"Signed in as @{user.username}.")
            return redirect(next_url)
    else:
        form = LoginForm(request)

    return render(request, 'accounts/login.html', {'form': form, 'next': next_url})


@require_http_methods(['GET', 'POST'])
def logout_view(request):
    """Terminate the authenticated session."""
    if request.user.is_authenticated:
        auth_logout(request)
        messages.info(request, "You have been logged out.")
    return redirect('accounts:login')
