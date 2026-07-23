from django.core.management.base import BaseCommand

from apps.core.alertas import verificar_queda_producao


class Command(BaseCommand):
    help = "Compara médias de produção e atualiza alertas de redução."

    def handle(self, *args: object, **options: object) -> None:
        total = verificar_queda_producao()
        self.stdout.write(self.style.SUCCESS(f"{total} reduções de produção observadas."))
