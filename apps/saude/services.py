from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import EventoSaude, ProdutoSaude, Tratamento

CAMPOS_EVENTO_EDITAVEIS = (
    "animal",
    "tipo",
    "data_hora",
    "titulo",
    "descricao",
    "veterinario",
    "responsavel",
    "resultado",
)


def _atribuir(instance: Any, dados: Mapping[str, Any], campos: Iterable[str]) -> None:
    for campo in campos:
        if campo in dados:
            setattr(instance, campo, dados[campo])


@transaction.atomic
def salvar_produto(*, instancia: ProdutoSaude | None = None, **dados: Any) -> ProdutoSaude:
    if instancia and not instancia._state.adding:
        produto = ProdutoSaude.objects.select_for_update().get(pk=instancia.pk)
    else:
        produto = ProdutoSaude()
    _atribuir(
        produto,
        dados,
        (
            "nome",
            "tipo",
            "fabricante",
            "unidade",
            "carencia_padrao_dias",
            "carencia_padrao_horas",
            "observacoes",
            "ativo",
        ),
    )
    produto.full_clean()
    produto.save()
    return produto


@transaction.atomic
def salvar_tratamento(*, instancia: Tratamento | None = None, **dados: Any) -> Tratamento:
    if instancia and not instancia._state.adding:
        tratamento = Tratamento.objects.select_for_update().get(pk=instancia.pk)
        campos_criticos = {
            "animal",
            "produto",
            "data_hora",
            "dose",
            "unidade",
            "carencia_dias",
            "carencia_horas",
        }
        mudou = any(
            campo in dados and dados[campo] != getattr(tratamento, campo)
            for campo in campos_criticos
        )
        if mudou and not str(dados.get("motivo_correcao", "")).strip():
            raise ValidationError(
                {"motivo_correcao": "A correção do tratamento exige justificativa."}
            )
        if mudou:
            dados["situacao"] = Tratamento.Situacao.CORRIGIDO
    else:
        tratamento = Tratamento()

    produto = dados.get("produto", getattr(tratamento, "produto", None))
    if produto and not instancia:
        dados.setdefault("unidade", produto.unidade)
        dados.setdefault("carencia_dias", produto.carencia_padrao_dias)
        dados.setdefault("carencia_horas", produto.carencia_padrao_horas)
        if not produto.ativo:
            raise ValidationError({"produto": "Selecione um produto ativo."})
    _atribuir(
        tratamento,
        dados,
        (
            "animal",
            "produto",
            "data_hora",
            "dose",
            "unidade",
            "responsavel",
            "motivo",
            "carencia_dias",
            "carencia_horas",
            "observacoes",
            "situacao",
            "motivo_correcao",
        ),
    )
    tratamento.full_clean()
    tratamento.save()
    return tratamento


@transaction.atomic
def cancelar_tratamento(*, tratamento: Tratamento, motivo: str) -> Tratamento:
    if not motivo.strip():
        raise ValidationError({"motivo": "O cancelamento exige justificativa."})
    tratamento = Tratamento.objects.select_for_update().get(pk=tratamento.pk)
    tratamento.situacao = Tratamento.Situacao.CANCELADO
    tratamento.motivo_cancelamento = motivo
    tratamento.ativo_registro = False
    tratamento.cancelado_em = timezone.now()
    tratamento.full_clean()
    tratamento.save()
    return tratamento


@transaction.atomic
def registrar_descarte_leite(
    *,
    tratamento: Tratamento,
    quantidade_litros: Any,
    data: Any | None = None,
    observacoes: str = "",
) -> Any:
    from apps.leite.models import DestinoLeite
    from apps.leite.services import salvar_destino

    tratamento = (
        Tratamento.objects.select_for_update().select_related("animal").get(pk=tratamento.pk)
    )
    if getattr(tratamento.animal, "sexo", None) != "F":
        raise ValidationError("O descarte de leite só pode ser associado a uma fêmea.")
    return salvar_destino(
        data=data or timezone.localdate(),
        tratamento=tratamento,
        tipo=DestinoLeite.Tipo.DESCARTE,
        quantidade_litros=quantidade_litros,
        observacoes=observacoes or f"Descarte relacionado ao tratamento {tratamento}.",
    )


def _bloquear_animal(animal: Any) -> Any:
    from apps.rebanho.models import Animal

    if animal is None:
        raise ValidationError({"animal": "Selecione o animal."})
    return Animal.objects.select_for_update().get(pk=animal.pk)


@transaction.atomic
def registrar_evento_saude(**dados: Any) -> EventoSaude:
    dados["animal"] = _bloquear_animal(dados.get("animal"))
    evento = EventoSaude(
        situacao=EventoSaude.Situacao.REGISTRADO,
        ativo_registro=True,
        cancelado_em=None,
    )
    _atribuir(evento, dados, CAMPOS_EVENTO_EDITAVEIS)
    evento.full_clean()
    evento.save()
    return evento


@transaction.atomic
def corrigir_evento_saude(*, evento: EventoSaude, motivo: str, **dados: Any) -> EventoSaude:
    evento = EventoSaude.objects.select_for_update().get(pk=evento.pk)
    if evento.cancelado or not evento.ativo_registro:
        raise ValidationError("Um evento cancelado não pode ser corrigido.")

    alteracoes = {
        campo: valor
        for campo, valor in dados.items()
        if campo in CAMPOS_EVENTO_EDITAVEIS and valor != getattr(evento, campo)
    }
    if not alteracoes:
        return evento
    if not motivo.strip():
        raise ValidationError({"motivo_correcao": "A correção do evento exige uma justificativa."})
    if "animal" in alteracoes:
        alteracoes["animal"] = _bloquear_animal(alteracoes["animal"])

    _atribuir(evento, alteracoes, CAMPOS_EVENTO_EDITAVEIS)
    evento.situacao = EventoSaude.Situacao.CORRIGIDO
    evento.motivo_correcao = motivo.strip()
    evento.full_clean()
    evento.save()
    return evento


def salvar_evento_saude(*, instancia: EventoSaude | None = None, **dados: Any) -> EventoSaude:
    """Entrada única para ModelForms, delegando às operações explícitas de domínio."""

    if instancia and not instancia._state.adding:
        motivo = str(dados.pop("motivo_correcao", ""))
        return corrigir_evento_saude(evento=instancia, motivo=motivo, **dados)
    dados.pop("motivo_correcao", None)
    return registrar_evento_saude(**dados)


@transaction.atomic
def cancelar_evento_saude(*, evento: EventoSaude, motivo: str) -> EventoSaude:
    if not motivo.strip():
        raise ValidationError({"motivo": "O cancelamento exige uma justificativa."})
    evento = EventoSaude.objects.select_for_update().get(pk=evento.pk)
    if evento.cancelado or not evento.ativo_registro:
        raise ValidationError("Este evento já foi cancelado.")

    evento.situacao = EventoSaude.Situacao.CANCELADO
    evento.motivo_cancelamento = motivo.strip()
    evento.ativo_registro = False
    evento.cancelado_em = timezone.now()
    evento.full_clean()
    evento.save()
    return evento
