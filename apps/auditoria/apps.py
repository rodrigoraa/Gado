from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auditoria"
    verbose_name = "Auditoria"

    def ready(self) -> None:
        from . import signals  # noqa: F401
