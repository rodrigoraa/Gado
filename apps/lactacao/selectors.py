from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Min, Q, QuerySet, Sum
from django.utils import timezone

from apps.rebanho.models import Animal

from .models import Lactacao

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class IndicadoresLactacao:
    producao_acumulada: Decimal = ZERO
    media_diaria: Decimal = ZERO
    maior_producao_diaria: Decimal = ZERO
    menor_producao_diaria: Decimal = ZERO
    dias_com_registro: int = 0
    producao_ultimos_sete_dias: Decimal = ZERO


def listar_lactacoes(*, situacao: str = "", busca: str = "") -> QuerySet[Lactacao]:
    queryset = Lactacao.objects.select_related("vaca", "parto")
    if situacao in Lactacao.Situacao.values:
        queryset = queryset.filter(situacao=situacao)
    if busca := busca.strip():
        queryset = queryset.filter(
            Q(vaca__identificacao__icontains=busca)
            | Q(vaca__identificacao_provisoria__icontains=busca)
            | Q(vaca__nome__icontains=busca)
        )
    return queryset.order_by("-data_inicio", "-criado_em")


def obter_lactacao(*, lactacao_id: str) -> Lactacao:
    return Lactacao.objects.select_related("vaca", "parto").get(pk=lactacao_id)


def lactacoes_ativas() -> QuerySet[Lactacao]:
    """Fonte única da lista de vacas aptas a aparecer na ordenha."""

    return (
        Lactacao.objects.filter(
            situacao=Lactacao.Situacao.ATIVA,
            vaca__situacao=Animal.Situacao.ATIVO,
        )
        .select_related("vaca", "vaca__lote")
        .order_by("vaca__identificacao", "vaca__nome")
    )


def lactacao_ativa_da_vaca(*, vaca: Animal) -> Lactacao | None:
    return lactacoes_ativas().filter(vaca=vaca).first()


def indicadores_lactacao(*, lactacao: Lactacao) -> IndicadoresLactacao:
    """Calcula sobre produções válidas; funciona mesmo antes do app leite migrar."""

    try:
        producoes = lactacao.producoes.exclude(ordenha__situacao="CANCELADA")
        acumulado = producoes.aggregate(valor=Sum("quantidade_litros"))["valor"] or ZERO
        diarios = (
            producoes.values("ordenha__data").annotate(total=Sum("quantidade_litros")).order_by()
        )
        resumo = diarios.aggregate(
            maior=Max("total"), menor=Min("total"), dias=Count("ordenha__data")
        )
        dias = int(resumo["dias"] or 0)
        limite = timezone.localdate() - timedelta(days=6)
        ultimos_sete = (
            producoes.filter(ordenha__data__gte=limite).aggregate(valor=Sum("quantidade_litros"))[
                "valor"
            ]
            or ZERO
        )
        return IndicadoresLactacao(
            producao_acumulada=acumulado,
            media_diaria=(acumulado / Decimal(dias)) if dias else ZERO,
            maior_producao_diaria=resumo["maior"] or ZERO,
            menor_producao_diaria=resumo["menor"] or ZERO,
            dias_com_registro=dias,
            producao_ultimos_sete_dias=ultimos_sete,
        )
    except (AttributeError, TypeError):
        return IndicadoresLactacao()


def comparar_lactacoes(*, vaca: Animal) -> list[dict[str, object]]:
    return [
        {"lactacao": lactacao, "indicadores": indicadores_lactacao(lactacao=lactacao)}
        for lactacao in listar_lactacoes().filter(vaca=vaca)
    ]
