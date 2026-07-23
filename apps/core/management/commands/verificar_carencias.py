from django.core.management.base import BaseCommand

from apps.core.alertas import verificar_carencias


class Command(BaseCommand):
    help = "Atualiza alertas de animais em período de carência."

    def handle(self, *args: object, **options: object) -> None:
        total = verificar_carencias()
        self.stdout.write(self.style.SUCCESS(f"{total} carências ativas encontradas."))
