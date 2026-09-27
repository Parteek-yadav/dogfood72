"""
ASGI config for Dogfood 2026 portal project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal.settings')

application = get_asgi_application()
