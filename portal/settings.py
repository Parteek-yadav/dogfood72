"""
Django settings for Dogfood 2026 portal project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-dogfood2026-hackathon-platform-dev-key'
)

DEBUG = os.environ.get('DEBUG', '1').lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,0.0.0.0,web,testserver'
    ).split(',')
    if host.strip()
]
if DEBUG and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('*')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'drf_spectacular',
    'django_htmx',

    # Local apps
    'core.apps.CoreConfig',
    'accounts.apps.AccountsConfig',
    'events.apps.EventsConfig',
    'teams.apps.TeamsConfig',
    'submissions.apps.SubmissionsConfig',
    'judging.apps.JudgingConfig',
    'voting.apps.VotingConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'portal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'portal.wsgi.application'
ASGI_APPLICATION = 'portal.asgi.application'

# Database
# In Docker, connects to Postgres ('db'). For local tests or fallback if host is unresolvable, uses SQLite.
import socket
import sys

is_testing = 'test' in sys.argv

if is_testing or os.environ.get('USE_SQLITE', '0').lower() in ('1', 'true', 'yes'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:' if is_testing else BASE_DIR / 'db.sqlite3',
        }
    }
else:
    pg_host = os.environ.get('POSTGRES_HOST', 'db')
    can_resolve = True
    try:
        socket.gethostbyname(pg_host)
    except socket.error:
        can_resolve = False

    if can_resolve:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': os.environ.get('POSTGRES_DB', 'dogfood'),
                'USER': os.environ.get('POSTGRES_USER', 'dogfood_user'),
                'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'dogfood_pass'),
                'HOST': pg_host,
                'PORT': os.environ.get('POSTGRES_PORT', '5432'),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'events:event_list'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework & OpenAPI Docs
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Dogfood 2026 Hackathon API',
    'DESCRIPTION': 'Dogfood 2026 hackathon submission-and-judging platform API.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {
        'EventRoleChoiceEnum': 'events.models.EventRole.Role',
        'TeamMembershipRoleChoiceEnum': 'teams.models.TeamMembership.Role',
        'SubmissionStatusChoiceEnum': 'submissions.models.Submission.Status',
        'JudgeAssignmentStatusChoiceEnum': 'judging.models.JudgeAssignment.Status',
    },
}
