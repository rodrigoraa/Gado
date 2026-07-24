from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.models import ConfiguracaoSistema
from apps.rebanho.models import Animal

from .models import Cobertura, DiagnosticoGestacao, Parto, PerdaGestacional


def listar_coberturas(
    *,
    busca: str = "",
    situacao: str = "",
    inicio: date | None = None,
    fim: date | None = None,
    incluir_canceladas: bool = False,
) -> QuerySet[Cobertura]:
    queryset = Cobertura.objects.select_related("vaca", "touro")
    if busca := busca.strip():
        queryset = queryset.filter(
            Q(vaca__identificacao__icontains=busca)
            | Q(vaca__identificacao_provisoria__icontains=busca)
            | Q(vaca__nome__icontains=busca)
            | Q(touro__nome__icontains=busca)
        )
    if situacao in Cobertura.Situacao.values:
        queryset = queryset.filter(situacao=situacao)
    elif not incluir_canceladas:
        queryset = queryset.exclude(situacao=Cobertura.Situacao.CANCELADA)
    if inicio:
        queryset = queryset.filter(data__gte=inicio)
    if fim:
        queryset = queryset.filter(data__lte=fim)
    return queryset.order_by("-data", "-criado_em")


def listar_coberturas_por_touro(*, busca: str = "") -> QuerySet[Cobertura]:
    queryset = (
        Cobertura.objects.filter(touro__isnull=False)
        .exclude(situacao=Cobertura.Situacao.CANCELADA)
        .select_related("vaca", "touro")
    )
    if busca := busca.strip():
        queryset = queryset.filter(touro__nome__icontains=busca)
    return queryset.order_by("touro__nome", "-data", "-criado_em")


def obter_cobertura(*, cobertura_id: str) -> Cobertura:
    return (
        Cobertura.objects.select_related("vaca", "touro")
        .prefetch_related(
            "diagnosticos",
            "perdas_gestacionais",
            "partos__nascimentos__animal",
            "historico",
        )
        .get(pk=cobertura_id)
    )


def coberturas_abertas(*, vaca: Animal | None = None) -> QuerySet[Cobertura]:
    queryset = Cobertura.objects.filter(situacao__in=Cobertura.SITUACOES_ABERTAS).select_related(
        "vaca", "touro"
    )
    return queryset.filter(vaca=vaca) if vaca else queryset


def coberturas_sem_diagnostico() -> QuerySet[Cobertura]:
    try:
        dias = int(ConfiguracaoSistema.obter().dias_diagnostico)
    except Exception:
        dias = 30
    limite = timezone.localdate() - timedelta(days=dias)
    return coberturas_abertas().filter(data__lte=limite, diagnosticos__isnull=True).distinct()


def partos_previstos(*, inicio: date | None = None, fim: date | None = None) -> QuerySet[Cobertura]:
    inicio = inicio or timezone.localdate()
    fim = fim or (inicio + timedelta(days=30))
    return (
        coberturas_abertas()
        .filter(
            previsao_atual_parto__range=(inicio, fim),
            situacao=Cobertura.Situacao.PRENHEZ_CONFIRMADA,
        )
        .order_by("previsao_atual_parto")
    )


def listar_partos(*, vaca: Animal | None = None) -> QuerySet[Parto]:
    queryset = Parto.objects.select_related("vaca", "cobertura").prefetch_related(
        "nascimentos__animal"
    )
    if vaca:
        queryset = queryset.filter(vaca=vaca)
    return queryset.order_by("-data_hora", "-criado_em")


def obter_parto(*, parto_id: str) -> Parto:
    return (
        Parto.objects.select_related("vaca", "cobertura")
        .prefetch_related("nascimentos__animal", "historico")
        .get(pk=parto_id)
    )


def historico_reprodutivo(*, vaca: Animal) -> list[dict[str, Any]]:
    eventos: list[dict[str, Any]] = []
    eventos.extend(
        {
            "data": cobertura.data,
            "tipo": "cobertura",
            "titulo": cobertura.get_tipo_display(),
            "descricao": cobertura.get_situacao_display(),
            "objeto": cobertura,
        }
        for cobertura in listar_coberturas(busca="", incluir_canceladas=True).filter(vaca=vaca)
    )
    eventos.extend(
        {
            "data": diagnostico.data,
            "tipo": "diagnostico",
            "titulo": "Diagnóstico de gestação",
            "descricao": diagnostico.get_resultado_display(),
            "objeto": diagnostico,
        }
        for diagnostico in DiagnosticoGestacao.objects.filter(vaca=vaca)
    )
    eventos.extend(
        {
            "data": perda.data,
            "tipo": "perda",
            "titulo": "Perda gestacional",
            "descricao": perda.get_tipo_display(),
            "objeto": perda,
        }
        for perda in PerdaGestacional.objects.filter(vaca=vaca)
    )
    eventos.extend(
        {
            "data": parto.data_hora.date(),
            "tipo": "parto",
            "titulo": "Parto",
            "descricao": parto.get_resultado_display(),
            "objeto": parto,
        }
        for parto in listar_partos(vaca=vaca)
    )
    return sorted(eventos, key=lambda evento: evento["data"], reverse=True)
