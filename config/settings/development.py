from .base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
