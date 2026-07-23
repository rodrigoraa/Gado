from __future__ import annotations

from typing import Any

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from apps.auditoria.context import obter_request
from apps.auditoria.services import registrar_auditoria

from .models import FechamentoLeite


@receiver(m2m_changed, sender=FechamentoLeite.entregas.through)
def auditar_entregas_fechamento(
    sender: type,
    instance: FechamentoLeite,
    action: str,
    reverse: bool,
    model: type,
    pk_set: set[object] | None,
    **kwargs: Any,
) -> None:
    del sender, model, kwargs
    if reverse or action not in {"post_add", "post_remove", "post_clear"}:
        return
    try:
        registrar_auditoria(
            modulo="financeiro",
            entidade="fechamentoleite",
            identificador=instance.pk,
            operacao="vinculo_entregas",
            dados_novos={
                "acao": action,
                "entregas": sorted(str(pk) for pk in (pk_set or set())),
            },
            justificativa=instance.motivo_ajuste,
            request=obter_request(),
        )
    except Exception:
        # O sinal não deve impedir migrations iniciais ou recuperação do banco.
        return
