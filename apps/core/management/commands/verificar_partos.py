from django.core.management.base import BaseCommand

from apps.core.alertas import verificar_diagnosticos, verificar_partos


class Command(BaseCommand):
    help = "Atualiza alertas de parto e coberturas sem diagnóstico."

    def handle(self, *args: object, **options: object) -> None:
        partos = verificar_partos()
        diagnosticos = verificar_diagnosticos()
        self.stdout.write(
            self.style.SUCCESS(f"Alertas: {partos} partos e {diagnosticos} diagnósticos pendentes.")
        )
