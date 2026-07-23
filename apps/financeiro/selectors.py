from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import DecimalField, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.leite.models import DestinoLeite
from apps.leite.selectors import total_produzido

from .models import EntregaLeite, FechamentoLeite, Laticinio, PrecoLeite, RecebimentoLeite
from .services import obter_preco_vigente

DINHEIRO: DecimalField[Decimal, Decimal] = DecimalField(max_digits=16, decimal_places=2)
LITROS: DecimalField[Decimal, Decimal] = DecimalField(max_digits=16, decimal_places=3)


def laticinio_ativo() -> Laticinio | None:
    return Laticinio.objects.filter(ativo=True).first()


def preco_vigente(*, dia: date | None = None) -> PrecoLeite | None:
    laticinio = laticinio_ativo()
    if not laticinio:
        return None
    return obter_preco_vigente(laticinio=laticinio, dia=dia or timezone.localdate())


def listar_entregas(
    *, data_inicial: date | None = None, data_final: date | None = None
) -> QuerySet[EntregaLeite]:
    queryset = EntregaLeite.objects.filter(ativo_registro=True).select_related("laticinio")
    if data_inicial:
        queryset = queryset.filter(data_coleta__date__gte=data_inicial)
    if data_final:
        queryset = queryset.filter(data_coleta__date__lte=data_final)
    return queryset


def listar_fechamentos() -> QuerySet[FechamentoLeite]:
    return (
        FechamentoLeite.objects.filter(ativo_registro=True)
        .select_related("laticinio")
        .prefetch_related("entregas", "recebimentos")
    )


def pagamentos_atrasados(*, hoje: date | None = None) -> QuerySet[FechamentoLeite]:
    hoje = hoje or timezone.localdate()
    return listar_fechamentos().filter(
        data_prevista_pagamento__lt=hoje,
        situacao__in=(
            FechamentoLeite.Situacao.FECHADO,
            FechamentoLeite.Situacao.DIVERGENTE,
            FechamentoLeite.Situacao.PARCIALMENTE_PAGO,
        ),
    )


def conferencia_mensal(*, ano: int, mes: int) -> dict[str, Any]:
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    entregas = listar_entregas(data_inicial=inicio, data_final=fim)
    totais_entrega = entregas.aggregate(
        litros=Coalesce(Sum("quantidade_litros"), Value(Decimal("0.000")), output_field=LITROS),
        bruto=Coalesce(Sum("valor_bruto"), Value(Decimal("0.00")), output_field=DINHEIRO),
        bonificacoes=Coalesce(
            Sum("total_bonificacoes"), Value(Decimal("0.00")), output_field=DINHEIRO
        ),
        descontos=Coalesce(Sum("total_descontos"), Value(Decimal("0.00")), output_field=DINHEIRO),
        liquido=Coalesce(Sum("valor_liquido"), Value(Decimal("0.00")), output_field=DINHEIRO),
    )
    destinado = DestinoLeite.objects.filter(
        data__range=(inicio, fim), tipo=DestinoLeite.Tipo.LATICINIO
    ).aggregate(
        total=Coalesce(Sum("quantidade_litros"), Value(Decimal("0.000")), output_field=LITROS)
    )["total"]
    fechamentos = listar_fechamentos().filter(competencia=inicio)
    totais_fechamentos = fechamentos.aggregate(
        litros=Coalesce(
            Sum("total_litros_calculado"), Value(Decimal("0.000")), output_field=LITROS
        ),
        liquido=Coalesce(
            Sum("valor_liquido_calculado"), Value(Decimal("0.00")), output_field=DINHEIRO
        ),
    )
    recebimentos = RecebimentoLeite.objects.filter(
        fechamento__in=fechamentos, situacao=RecebimentoLeite.Situacao.CONFIRMADO
    ).aggregate(total=Coalesce(Sum("valor"), Value(Decimal("0.00")), output_field=DINHEIRO))[
        "total"
    ]
    produzido = total_produzido(data_inicial=inicio, data_final=fim)
    preco_medio_bruto = (
        totais_entrega["bruto"] / totais_entrega["litros"]
        if totais_entrega["litros"]
        else Decimal("0")
    )
    preco_medio_liquido = (
        totais_entrega["liquido"] / totais_entrega["litros"]
        if totais_entrega["litros"]
        else Decimal("0")
    )
    return {
        "competencia": inicio,
        "produzido": produzido,
        "destinado_laticinio": destinado,
        "entregue": totais_entrega["litros"],
        "diferenca_destinado_entregue": destinado - totais_entrega["litros"],
        "quantidade_coletas": entregas.count(),
        "quantidade_fechamentos": fechamentos.count(),
        "litros_em_fechamentos": totais_fechamentos["litros"],
        "valor_em_fechamentos": totais_fechamentos["liquido"],
        "fechamentos_divergentes": fechamentos.filter(
            situacao=FechamentoLeite.Situacao.DIVERGENTE
        ).count(),
        "valor_bruto": totais_entrega["bruto"],
        "bonificacoes": totais_entrega["bonificacoes"],
        "descontos": totais_entrega["descontos"],
        "valor_liquido": totais_entrega["liquido"],
        "preco_medio_bruto": preco_medio_bruto,
        "preco_medio_liquido": preco_medio_liquido,
        "valor_recebido": recebimentos,
        "saldo_pendente": totais_entrega["liquido"] - recebimentos,
        "fechamentos": fechamentos,
    }
