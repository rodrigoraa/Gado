from __future__ import annotations

from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from apps.core.backup_status import registrar_backup_sucesso


class Command(BaseCommand):
    help = "Registra o marcador persistente de um backup concluído e verificado."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--arquivo",
            required=True,
            help="Nome do pacote final já publicado pelo script de backup.",
        )

    def handle(self, *args: object, **options: object) -> None:
        arquivo = options.get("arquivo")
        if not isinstance(arquivo, str):
            raise CommandError("Informe o nome do pacote final em --arquivo.")
        try:
            status = registrar_backup_sucesso(arquivo)
        except (OSError, ValueError) as exc:
            raise CommandError(f"Não foi possível registrar o backup: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Backup registrado: {status.arquivo} em {status.concluido_em.isoformat()}"
            )
        )
