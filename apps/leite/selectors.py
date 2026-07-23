from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, DecimalField, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import ConfiguracaoSistema

from .models import DestinoLeite, Ordenha, ProducaoAnimal

DECIMAL_LITROS: DecimalField[Decimal, Decimal] = DecimalField(max_digits=14, decimal_places=3)


def listar_ordenhas(
    *, data_inicial: date | None = None, data_final: date | None = None
) -> QuerySet[Ordenha]:
    queryset = (
        Ordenha.objects.filter(ativo_registro=True)
        .exclude(situacao=Ordenha.Situacao.CANCELADA)
        .select_related("lote")
        .prefetch_related("producoes__vaca")
    )
    if data_inicial:
        queryset = queryset.filter(data__gte=data_inicial)
    if data_final:
        queryset = queryset.filter(data__lte=data_final)
    return queryset


def listar_destinos(
    *, data_inicial: date | None = None, data_final: date | None = None
) -> QuerySet[DestinoLeite]:
    queryset = DestinoLeite.objects.select_related("ordenha", "tratamento").all()
    if data_inicial:
        queryset = queryset.filter(data__gte=data_inicial)
    if data_final:
        queryset = queryset.filter(data__lte=data_final)
    return queryset


def total_produzido(*, data_inicial: date, data_final: date) -> Decimal:
    return listar_ordenhas(data_inicial=data_inicial, data_final=data_final).aggregate(
        total=Coalesce(
            Sum("quantidade_total"), Value(Decimal("0.000")), output_field=DECIMAL_LITROS
        )
    )["total"]


def total_por_periodo(*, dia: date) -> dict[str, Decimal]:
    linhas = (
        listar_ordenhas(data_inicial=dia, data_final=dia)
        .values("periodo")
        .annotate(
            total=Coalesce(
                Sum("quantidade_total"), Value(Decimal("0.000")), output_field=DECIMAL_LITROS
            )
        )
    )
    resultado = {chave: Decimal("0.000") for chave, _ in Ordenha.Periodo.choices}
    resultado.update({linha["periodo"]: linha["total"] for linha in linhas})
    return resultado


def resumo_mensal(*, ano: int, mes: int) -> dict[str, Decimal | int]:
    ordenhas = listar_ordenhas().filter(data__year=ano, data__month=mes)
    agregado = ordenhas.aggregate(
        total=Coalesce(
            Sum("quantidade_total"), Value(Decimal("0.000")), output_field=DECIMAL_LITROS
        ),
        dias=Count("data", distinct=True),
    )
    agregado["vacas"] = ProducaoAnimal.objects.filter(ordenha__in=ordenhas).aggregate(
        total=Count("vaca", distinct=True)
    )["total"]
    dias = agregado["dias"] or 0
    agregado["media_diaria"] = agregado["total"] / dias if dias else Decimal("0.000")
    return agregado


def conciliacao_dia(*, dia: date) -> dict[str, Decimal]:
    produzido = total_produzido(data_inicial=dia, data_final=dia)
    destinado = DestinoLeite.objects.filter(data=dia).aggregate(
        total=Coalesce(
            Sum("quantidade_litros"), Value(Decimal("0.000")), output_field=DECIMAL_LITROS
        )
    )["total"]
    return {"produzido": produzido, "destinado": destinado, "diferenca": produzido - destinado}


def vacas_disponiveis_ordenha() -> QuerySet[Any]:
    from apps.lactacao.models import Lactacao

    return Lactacao.objects.filter(situacao=Lactacao.Situacao.ATIVA).select_related(
        "vaca", "vaca__lote"
    )


def vacas_em_carencia(*, momento: datetime | None = None) -> QuerySet[Any]:
    from apps.saude.models import Tratamento

    momento = momento or timezone.now()
    return (
        Tratamento.objects.filter(
            ativo_registro=True,
            data_hora__lte=momento,
            data_liberacao__gt=momento,
        )
        .exclude(situacao=Tratamento.Situacao.CANCELADO)
        .select_related("animal", "produto")
    )


def detectar_quedas_producao(*, data_referencia: date | None = None) -> list[dict[str, Any]]:
    data_referencia = data_referencia or timezone.localdate()
    # O dia corrente pode estar incompleto. Comparamos os tres ultimos dias
    # encerrados com os sete dias imediatamente anteriores.
    fim_recente = data_referencia - timedelta(days=1)
    inicio_recente = data_referencia - timedelta(days=3)
    fim_base = data_referencia - timedelta(days=4)
    inicio_base = fim_base - timedelta(days=6)
    configuracao = ConfiguracaoSistema.obter()

    ids_vacas = (
        ProducaoAnimal.objects.filter(
            ordenha__ativo_registro=True,
            ordenha__data__range=(inicio_base, fim_recente),
        )
        .exclude(ordenha__situacao=Ordenha.Situacao.CANCELADA)
        .values_list("vaca_id", flat=True)
        .distinct()
    )
    alertas: list[dict[str, Any]] = []
    for vaca_id in ids_vacas:
        base = (
            ProducaoAnimal.objects.filter(
                vaca_id=vaca_id,
                ordenha__ativo_registro=True,
                ordenha__data__range=(inicio_base, fim_base),
            )
            .exclude(ordenha__situacao=Ordenha.Situacao.CANCELADA)
            .aggregate(total=Sum("quantidade_litros"), dias=Count("ordenha__data", distinct=True))
        )
        recente = (
            ProducaoAnimal.objects.filter(
                vaca_id=vaca_id,
                ordenha__ativo_registro=True,
                ordenha__data__range=(inicio_recente, fim_recente),
            )
            .exclude(ordenha__situacao=Ordenha.Situacao.CANCELADA)
            .aggregate(total=Sum("quantidade_litros"), dias=Count("ordenha__data", distinct=True))
        )
        if (base["dias"] or 0) < 4 or (recente["dias"] or 0) < 2 or not base["total"]:
            continue
        media_base = base["total"] / base["dias"]
        media_recente = recente["total"] / recente["dias"]
        queda = ((media_base - media_recente) / media_base * Decimal("100")).quantize(
            Decimal("0.01")
        )
        if queda > configuracao.queda_producao_percentual:
            alertas.append(
                {
                    "vaca_id": vaca_id,
                    "media_anterior": media_base,
                    "media_recente": media_recente,
                    "queda_percentual": queda,
                }
            )
    return alertas
