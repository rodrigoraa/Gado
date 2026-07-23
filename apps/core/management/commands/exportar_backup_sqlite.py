from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Cria uma cópia consistente e verificada do banco SQLite em uso."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--saida", required=True, help="Arquivo SQLite de destino.")

    def handle(self, *args: object, **options: object) -> None:
        if connection.vendor != "sqlite":
            raise CommandError("Este comando só pode ser usado com SQLite.")

        saida = Path(str(options["saida"])).expanduser().resolve()
        saida.parent.mkdir(parents=True, exist_ok=True)
        temporario = saida.with_name(f".{saida.name}.tmp")
        temporario.unlink(missing_ok=True)

        connection.ensure_connection()
        origem = connection.connection
        if origem is None:
            raise CommandError("A conexão SQLite não pôde ser aberta.")

        try:
            destino = sqlite3.connect(temporario)
            try:
                origem.backup(destino)
                resultado = destino.execute("PRAGMA integrity_check").fetchone()
                if not resultado or resultado[0] != "ok":
                    raise CommandError("A cópia SQLite não passou na verificação de integridade.")
            finally:
                destino.close()
            os.replace(temporario, saida)
            saida.chmod(0o600)
        finally:
            temporario.unlink(missing_ok=True)

        self.stdout.write(f"Backup SQLite criado e verificado: {saida.name}")
