from __future__ import annotations

import json
import logging
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .context import guardar_anterior, obter_request, retirar_anterior
from .models import RegistroAuditoria
from .services import registrar_auditoria

logger = logging.getLogger(__name__)

APPS_AUDITADOS = {
    "core",
    "rebanho",
    "reproducao",
    "lactacao",
    "leite",
    "financeiro",
    "saude",
}
IGNORAR_CAMPOS = {"criado_em", "atualizado_em"}


def _chave(instance: Model) -> str:
    return f"{instance._meta.label_lower}:{instance.pk}"


def _normalizar(valor: Any) -> Any:
    return json.loads(json.dumps(valor, cls=DjangoJSONEncoder))


def _snapshot(instance: Model) -> dict[str, Any]:
    dados: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORAR_CAMPOS:
            continue
        try:
            dados[field.name] = _normalizar(field.value_from_object(instance))
        except (TypeError, ValueError):
            dados[field.name] = str(field.value_from_object(instance))
    return dados


@receiver(pre_save)
def capturar_anterior(sender: type[Model], instance: Model, **kwargs: Any) -> None:
    if (
        sender is RegistroAuditoria
        or sender._meta.app_label not in APPS_AUDITADOS
        or not instance.pk
    ):
        return
    try:
        anterior = sender._default_manager.get(pk=instance.pk)
    except Exception:
        return
    guardar_anterior(_chave(instance), _snapshot(anterior))


@receiver(post_save)
def auditar_salvamento(
    sender: type[Model], instance: Model, created: bool, raw: bool = False, **kwargs: Any
) -> None:
    if raw or sender is RegistroAuditoria or sender._meta.app_label not in APPS_AUDITADOS:
        return
    anteriores = retirar_anterior(_chave(instance))
    novos = _snapshot(instance)
    if not created and anteriores == novos:
        return
    justificativa = ""
    for campo in (
        "motivo_cancelamento",
        "motivo_correcao",
        "motivo_ajuste",
        "motivo_alteracao",
        "justificativa_preco",
        "justificativa_excesso",
        "justificativa",
    ):
        valor = getattr(instance, campo, "")
        if valor:
            justificativa = str(valor)
            break
    request = obter_request()
    try:
        registrar_auditoria(
            modulo=sender._meta.app_label,
            entidade=sender._meta.model_name or sender.__name__.lower(),
            identificador=instance.pk,
            operacao="criacao" if created else "alteracao",
            dados_anteriores=anteriores,
            dados_novos=novos,
            justificativa=justificativa,
            request=request,
        )
    except Exception:
        logger.exception(
            "Falha ao registrar auditoria de %s:%s.",
            sender._meta.label_lower,
            instance.pk,
        )
        # Os services de negócio são atômicos: se a trilha obrigatória falhar,
        # a alteração principal também deve ser revertida, nunca confirmada sem rastro.
        raise
