from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

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
    queryset = DestinoLeite.objects.select_related("ordenha").all()
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
