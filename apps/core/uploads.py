from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.auditoria.context import obter_request

from .models import ArquivoAnexo


@dataclass(frozen=True, slots=True)
class DadosUpload:
    nome_original: str
    mime_type: str
    tamanho_bytes: int


def capturar_dados_upload(arquivo: object) -> DadosUpload | None:
    """Captura dados do UploadedFile antes que o storage substitua seu nome."""

    content_type = str(getattr(arquivo, "content_type", "") or "").strip().lower()
    nome = Path(str(getattr(arquivo, "name", "") or "")).name
    tamanho = getattr(arquivo, "size", None)
    if not nome or tamanho is None or not content_type:
        return None
    return DadosUpload(
        nome_original=nome[:255],
        mime_type=content_type[:120],
        tamanho_bytes=max(int(tamanho), 0),
    )


def _usuario_atual() -> Any | None:
    request = obter_request()
    usuario = getattr(request, "user", None)
    return usuario if getattr(usuario, "is_authenticated", False) else None


@transaction.atomic
def registrar_metadados_upload(
    *, objeto: Any, campo: str, arquivo_salvo: Any, dados: DadosUpload
) -> ArquivoAnexo:
    content_type = ContentType.objects.get_for_model(objeto, for_concrete_model=False)
    object_id = str(objeto.pk)
    anteriores = ArquivoAnexo.objects.select_for_update().filter(
        content_type=content_type,
        object_id=object_id,
        campo=campo,
        ativo=True,
    )
    for anterior in anteriores:
        anterior.ativo = False
        anterior.substituido_em = timezone.now()
        anterior.save(update_fields=("ativo", "substituido_em", "atualizado_em"))
    return ArquivoAnexo.objects.create(
        content_type=content_type,
        object_id=object_id,
        campo=campo,
        caminho=str(arquivo_salvo.name),
        nome_original=dados.nome_original,
        mime_type=dados.mime_type,
        tamanho_bytes=dados.tamanho_bytes,
        enviado_por=_usuario_atual(),
    )


@transaction.atomic
def desativar_metadados_upload(*, objeto: Any, campo: str) -> None:
    content_type = ContentType.objects.get_for_model(objeto, for_concrete_model=False)
    registros = ArquivoAnexo.objects.select_for_update().filter(
        content_type=content_type,
        object_id=str(objeto.pk),
        campo=campo,
        ativo=True,
    )
    for registro in registros:
        registro.ativo = False
        registro.substituido_em = timezone.now()
        registro.save(update_fields=("ativo", "substituido_em", "atualizado_em"))
