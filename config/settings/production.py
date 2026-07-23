from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
ENABLE_LAN_FALLBACK = env_bool("ENABLE_LAN_FALLBACK", False)  # noqa: F405
# O fallback de emergência usa HTTP em um IP privado. Mantê-lo desligado preserva
# cookies Secure e redirecionamento HTTPS na operação normal pelo domínio.
SESSION_COOKIE_SECURE = not ENABLE_LAN_FALLBACK
CSRF_COOKIE_SECURE = not ENABLE_LAN_FALLBACK
SECURE_SSL_REDIRECT = (
    False if ENABLE_LAN_FALLBACK else env_bool("DJANGO_SECURE_SSL_REDIRECT", True)  # noqa: F405
)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31_536_000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)  # noqa: F405
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)  # noqa: F405
SECURE_REDIRECT_EXEMPT = [r"^health/$", r"^health/live/$", r"^health/ready/$"]

if (  # noqa: F405
    len(SECRET_KEY) < 50 or SECRET_KEY.lower().startswith(("inseguro-", "troque", "change-me"))
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY deve ser aleatória, exclusiva e ter ao menos 50 caracteres."
    )
if not env("DJANGO_ALLOWED_HOSTS"):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS deve ser definido explicitamente.")
if not APP_DOMAIN:  # noqa: F405
    raise ImproperlyConfigured("APP_DOMAIN deve ser definido em produção.")
if APP_DOMAIN not in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("APP_DOMAIN também deve constar em DJANGO_ALLOWED_HOSTS.")
if f"https://{APP_DOMAIN}" not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured(
        "DJANGO_CSRF_TRUSTED_ORIGINS deve conter a origem HTTPS de APP_DOMAIN."
    )
