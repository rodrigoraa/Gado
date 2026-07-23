from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone


@dataclass(frozen=True)
class BackupStatus:
    concluido_em: datetime
    arquivo: str


def _status_path(path: Path | str | None = None) -> Path:
    return Path(path if path is not None else settings.BACKUP_STATUS_FILE)


def ler_backup_status(path: Path | str | None = None) -> BackupStatus | None:
    """Lê o último backup confirmado ou retorna ``None`` para marcador inválido."""

    try:
        payload = json.loads(_status_path(path).read_text(encoding="utf-8"))
        concluido_em = datetime.fromisoformat(payload["concluido_em"])
        arquivo = payload["arquivo"]
        if concluido_em.tzinfo is None or not isinstance(arquivo, str) or not arquivo:
            return None
    except (FileNotFoundError, OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
    return BackupStatus(concluido_em=concluido_em, arquivo=arquivo)


def registrar_backup_sucesso(
    arquivo: str,
    *,
    concluido_em: datetime | None = None,
    path: Path | str | None = None,
) -> BackupStatus:
    """Registra atomicamente um backup que já foi publicado e verificado."""

    nome_arquivo = Path(arquivo).name
    if not nome_arquivo:
        raise ValueError("O nome do arquivo de backup não pode ficar vazio.")

    momento = concluido_em or timezone.now()
    if momento.tzinfo is None:
        raise ValueError("A data do backup precisa possuir fuso horário.")

    destino = _status_path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "versao": 1,
        "concluido_em": momento.isoformat(),
        "arquivo": nome_arquivo,
    }

    descriptor, temporario_bruto = tempfile.mkstemp(
        dir=destino.parent,
        prefix=f".{destino.name}.",
        suffix=".tmp",
        text=True,
    )
    temporario = Path(temporario_bruto)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as arquivo_status:
            json.dump(payload, arquivo_status, ensure_ascii=False, separators=(",", ":"))
            arquivo_status.write("\n")
            arquivo_status.flush()
            os.fsync(arquivo_status.fileno())
        temporario.chmod(0o600)
        os.replace(temporario, destino)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise

    return BackupStatus(concluido_em=momento, arquivo=nome_arquivo)
