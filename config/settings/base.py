"""Configurações compartilhadas entre todos os ambientes."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).lower() in {"1", "true", "yes", "sim", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def env_path(name: str, default: Path) -> Path:
    path = Path(env(name, str(default)))
    return path if path.is_absolute() else BASE_DIR / path


SECRET_KEY = env("DJANGO_SECRET_KEY", "inseguro-apenas-desenvolvimento-troque-em-producao")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core.apps.CoreConfig",
    "apps.usuarios.apps.UsuariosConfig",
    "apps.rebanho.apps.RebanhoConfig",
    "apps.reproducao.apps.ReproducaoConfig",
    "apps.lactacao.apps.LactacaoConfig",
    "apps.leite.apps.LeiteConfig",
    "apps.saude.apps.SaudeConfig",
    "apps.financeiro.apps.FinanceiroConfig",
    "apps.relatorios.apps.RelatoriosConfig",
    "apps.auditoria.apps.AuditoriaConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.auditoria.middleware.AuditContextMiddleware",
    "apps.usuarios.middleware.UltimaAtividadeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.configuracao_global",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env_path("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "timeout": env_int("SQLITE_TIMEOUT_SECONDS", 30),
            "transaction_mode": "IMMEDIATE",
            "init_command": (
                "PRAGMA journal_mode=WAL;PRAGMA synchronous=NORMAL;PRAGMA foreign_keys=ON"
            ),
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Campo_Grande"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Arquivos de negócio passam por uma view autenticada; o proxy nunca expõe MEDIA_ROOT.
MEDIA_URL = "/arquivos/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

BACKUP_MONITOR_ENABLED = env_bool("BACKUP_MONITOR_ENABLED", True)
BACKUP_MAX_AGE_HOURS = max(1, env_int("BACKUP_MAX_AGE_HOURS", 36))
BACKUP_STATUS_FILE = env_path(
    "BACKUP_STATUS_FILE",
    MEDIA_ROOT / ".sistema" / "ultimo_backup.json",
)
DISK_MONITOR_ENABLED = env_bool("DISK_MONITOR_ENABLED", True)
DISK_MONITOR_PATH = env_path("DISK_MONITOR_PATH", MEDIA_ROOT)
DISK_MIN_FREE_PERCENT = min(100, max(1, env_int("DISK_MIN_FREE_PERCENT", 10)))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "login"

APP_DOMAIN = env("APP_DOMAIN")
APP_BASE_URL = env("APP_BASE_URL", f"https://{APP_DOMAIN}" if APP_DOMAIN else "")
PAGINATE_BY = env_int("PAGINATE_BY", 20)
GESTACAO_DIAS_PADRAO = env_int("GESTACAO_DIAS_PADRAO", 283)
MARGEM_PARTO_DIAS_PADRAO = env_int("MARGEM_PARTO_DIAS_PADRAO", 7)
MAX_UPLOAD_BYTES = DATA_UPLOAD_MAX_MEMORY_SIZE
MAX_UPLOAD_SIZE = MAX_UPLOAD_BYTES

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"structured": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
