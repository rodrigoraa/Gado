from django.core.management.base import BaseCommand

from apps.core.alertas import verificar_todos


class Command(BaseCommand):
    help = "Atualiza todos os alertas operacionais do sistema."

    def handle(self, *args: object, **options: object) -> None:
        resultados = verificar_todos()
        resumo = ", ".join(f"{nome}: {quantidade}" for nome, quantidade in resultados.items())
        self.stdout.write(self.style.SUCCESS(f"Alertas atualizados — {resumo}"))
