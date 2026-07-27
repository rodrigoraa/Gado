from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import ConfiguracaoSistema

from .models import DestinoLeite, Ordenha, ProducaoAnimal

REGISTRO_AUTOMATICO = "Alteração registrada automaticamente pelo sistema."


def _atribuir(instance: Any, dados: Mapping[str, Any], campos: Iterable[str]) -> None:
    for campo in campos:
        if campo in dados:
            setattr(instance, campo, dados[campo])


def _configuracao() -> ConfiguracaoSistema:
    return ConfiguracaoSistema.obter()


@transaction.atomic
def salvar_ordenha(*, instancia: Ordenha | None = None, **dados: Any) -> Ordenha:
    if instancia and not instancia._state.adding:
        ordenha = Ordenha.objects.select_for_update().get(pk=instancia.pk)
        campos_criticos = {"data", "periodo", "quantidade_total", "quantidade_vacas", "lote"}
        alterou = any(
            campo in dados and dados[campo] != getattr(ordenha, campo) for campo in campos_criticos
        )
        if alterou:
            dados["situacao"] = Ordenha.Situacao.CORRIGIDA
            dados["motivo_correcao"] = (
                str(dados.get("motivo_correcao", "")).strip() or REGISTRO_AUTOMATICO
            )
    else:
        ordenha = Ordenha()

    if dados.get("quantidade_total") == 0 and not (
        str(dados.get("observacoes", "")).strip() or str(dados.get("motivo_correcao", "")).strip()
    ):
        dados["observacoes"] = REGISTRO_AUTOMATICO

    _atribuir(
        ordenha,
        dados,
        (
            "data",
            "periodo",
            "horario",
            "lote",
            "modo",
            "quantidade_total",
            "quantidade_vacas",
            "responsavel",
            "observacoes",
            "duplicidade_confirmada",
            "justificativa_divergencia",
            "motivo_correcao",
            "situacao",
        ),
    )
    ordenha.full_clean()
    ordenha.save()
    return ordenha


@transaction.atomic
def registrar_ordenha_com_producoes(
    *, dados_ordenha: Mapping[str, Any], producoes: Iterable[Mapping[str, Any]]
) -> Ordenha:
    ordenha = salvar_ordenha(**dict(dados_ordenha))
    for dados in producoes:
        registrar_producao(
            ordenha=ordenha,
            vaca=dados["vaca"],
            quantidade_litros=dados["quantidade_litros"],
            observacoes=dados.get("observacoes", ""),
        )
    conciliar_ordenha(ordenha=ordenha, justificativa=ordenha.justificativa_divergencia)
    return ordenha


@transaction.atomic
def registrar_producao(
    *,
    ordenha: Ordenha,
    vaca: Any,
    quantidade_litros: Decimal,
    observacoes: str = "",
) -> ProducaoAnimal:
    from apps.rebanho.models import Animal

    vaca = Animal.objects.select_for_update().get(pk=vaca.pk)
    if vaca.situacao != Animal.Situacao.ATIVO:
        raise ValidationError({"vaca": "A produção só pode ser lançada para um animal ativo."})

    ordenha = Ordenha.objects.select_for_update().get(pk=ordenha.pk)
    producao = ProducaoAnimal(
        ordenha=ordenha,
        vaca=vaca,
        quantidade_litros=quantidade_litros,
        observacoes=observacoes,
    )
    producao.full_clean()
    producao.save()
    if ordenha.modo == Ordenha.Modo.INDIVIDUAL:
        ordenha.quantidade_vacas = ordenha.producoes.values("vaca_id").distinct().count()
        ordenha.save(update_fields=("quantidade_vacas", "atualizado_em"))
    return producao


@transaction.atomic
def atualizar_producao(
    *,
    producao: ProducaoAnimal,
    quantidade_litros: Decimal,
    observacoes: str = "",
    justificativa: str = "",
) -> ProducaoAnimal:
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    producao = (
        ProducaoAnimal.objects.select_for_update().select_related("ordenha").get(pk=producao.pk)
    )
    producao.quantidade_litros = quantidade_litros
    producao.observacoes = observacoes
    producao.full_clean()
    producao.save()
    ordenha = producao.ordenha
    ordenha.situacao = Ordenha.Situacao.CORRIGIDA
    ordenha.motivo_correcao = justificativa
    ordenha.save(update_fields=("situacao", "motivo_correcao", "atualizado_em"))
    return producao


@transaction.atomic
def conciliar_ordenha(*, ordenha: Ordenha, justificativa: str = "") -> Ordenha:
    ordenha = Ordenha.objects.select_for_update().prefetch_related("producoes").get(pk=ordenha.pk)
    if ordenha.modo != Ordenha.Modo.INDIVIDUAL:
        return ordenha
    configuracao = _configuracao()
    excede_litros = abs(ordenha.diferenca_individual) > configuracao.tolerancia_divergencia_litros
    excede_percentual = (
        ordenha.diferenca_percentual > configuracao.tolerancia_divergencia_percentual
    )
    if excede_litros or excede_percentual:
        justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    ordenha.justificativa_divergencia = justificativa
    ordenha.save(update_fields=("justificativa_divergencia", "atualizado_em"))
    return ordenha


@transaction.atomic
def cancelar_ordenha(*, ordenha: Ordenha, motivo: str = "") -> Ordenha:
    motivo = motivo.strip() or REGISTRO_AUTOMATICO
    ordenha = Ordenha.objects.select_for_update().get(pk=ordenha.pk)
    if ordenha.destinos.exists():
        raise ValidationError(
            "A ordenha possui destinos vinculados. Corrija esses destinos antes de cancelar."
        )
    ordenha.situacao = Ordenha.Situacao.CANCELADA
    ordenha.motivo_cancelamento = motivo
    ordenha.ativo_registro = False
    ordenha.cancelado_em = timezone.now()
    ordenha.full_clean()
    ordenha.save()
    return ordenha


@transaction.atomic
def salvar_destino(*, instancia: DestinoLeite | None = None, **dados: Any) -> DestinoLeite:
    if instancia and not instancia._state.adding:
        destino = DestinoLeite.objects.select_for_update().get(pk=instancia.pk)
    else:
        destino = DestinoLeite()
    _atribuir(
        destino,
        dados,
        ("data", "ordenha", "tipo", "quantidade_litros", "observacoes"),
    )
    destino.full_clean()
    destino.save()
    return destino
