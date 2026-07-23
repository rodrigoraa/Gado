from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

EXTENSOES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".pdf"}
MIMES_PERMITIDOS = {"image/jpeg", "image/png", "application/pdf"}
MIME_POR_EXTENSAO = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def _cabecalho(arquivo: object, tamanho: int = 1024) -> bytes:
    """Lê a assinatura real e devolve o cursor à posição original."""
    try:
        posicao = arquivo.tell()  # type: ignore[attr-defined]
        arquivo.seek(0)  # type: ignore[attr-defined]
        conteudo = arquivo.read(tamanho)  # type: ignore[attr-defined]
        arquivo.seek(posicao)  # type: ignore[attr-defined]
    except (AttributeError, OSError, ValueError):
        return b""
    return bytes(conteudo)


def _assinatura_valida(extensao: str, cabecalho: bytes) -> bool:
    if extensao in {".jpg", ".jpeg"}:
        return cabecalho.startswith(b"\xff\xd8\xff")
    if extensao == ".png":
        return cabecalho.startswith(b"\x89PNG\r\n\x1a\n")
    if extensao == ".pdf":
        return b"%PDF-" in cabecalho
    return False


def validar_upload_privado(arquivo: object) -> None:
    nome = Path(str(getattr(arquivo, "name", ""))).name
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        raise ValidationError("Envie um arquivo JPG, JPEG, PNG ou PDF.")
    tamanho = int(getattr(arquivo, "size", 0))
    if tamanho <= 0 or tamanho > settings.MAX_UPLOAD_BYTES:
        limite_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(f"O arquivo deve ter até {limite_mb} MB.")
    mime_informado = str(getattr(arquivo, "content_type", ""))
    mime_estimado, _ = mimetypes.guess_type(nome)
    if mime_informado and mime_informado not in MIMES_PERMITIDOS:
        raise ValidationError("O tipo do arquivo não é permitido.")
    if mime_estimado not in MIMES_PERMITIDOS:
        raise ValidationError("A extensão e o tipo do arquivo não correspondem.")
    if mime_informado and mime_informado != MIME_POR_EXTENSAO[extensao]:
        raise ValidationError("A extensão e o tipo informado do arquivo não correspondem.")
    if not _assinatura_valida(extensao, _cabecalho(arquivo)):
        raise ValidationError("O conteúdo do arquivo não corresponde a JPG, PNG ou PDF válido.")


def validar_upload_imagem(arquivo: object) -> None:
    nome = Path(str(getattr(arquivo, "name", ""))).name
    if Path(nome).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValidationError("Envie uma imagem JPG, JPEG ou PNG.")
    validar_upload_privado(arquivo)
