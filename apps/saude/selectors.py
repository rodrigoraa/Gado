from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from django.db.models import QuerySet
from django.utils import timezone

from .models import EventoSaude, ProdutoSaude, Tratamento


def listar_produtos(*, somente_ativos: bool = True) -> QuerySet[ProdutoSaude]:
    queryset = ProdutoSaude.objects.all()
    return queryset.filter(ativo=True) if somente_ativos else queryset


def listar_tratamentos(
    *,
    animal_id: UUID | str | None = None,
    data_inicial: date | None = None,
    data_final: date | None = None,
) -> QuerySet[Tratamento]:
    queryset = (
        Tratamento.objects.filter(ativo_registro=True)
        .exclude(situacao=Tratamento.Situacao.CANCELADO)
        .select_related("animal", "produto")
    )
    if animal_id:
        queryset = queryset.filter(animal_id=animal_id)
    if data_inicial:
        queryset = queryset.filter(data_hora__date__gte=data_inicial)
    if data_final:
        queryset = queryset.filter(data_hora__date__lte=data_final)
    return queryset


def tratamentos_em_carencia(*, momento: datetime | None = None) -> QuerySet[Tratamento]:
    momento = momento or timezone.now()
    return listar_tratamentos().filter(data_hora__lte=momento, data_liberacao__gt=momento)


def animais_em_carencia(*, momento: datetime | None = None) -> QuerySet[Tratamento]:
    return (
        tratamentos_em_carencia(momento=momento)
        .order_by("animal_id", "-data_liberacao")
        .distinct("animal_id")
    )


def liberacoes_ate(*, dias: int = 7) -> QuerySet[Tratamento]:
    agora = timezone.now()
    return tratamentos_em_carencia(momento=agora).filter(
        data_liberacao__lte=agora + timedelta(days=dias)
    )


def listar_eventos_saude(
    *,
    animal_id: UUID | str | None = None,
    tipo: str | None = None,
    data_inicial: date | None = None,
    data_final: date | None = None,
    incluir_cancelados: bool = True,
) -> QuerySet[EventoSaude]:
    """Retorna o prontuário clínico; cancelados ficam visíveis por padrão."""

    queryset = EventoSaude.objects.select_related("animal")
    if not incluir_cancelados:
        queryset = queryset.filter(ativo_registro=True).exclude(
            situacao=EventoSaude.Situacao.CANCELADO
        )
    if animal_id:
        queryset = queryset.filter(animal_id=animal_id)
    if tipo:
        queryset = queryset.filter(tipo=tipo)
    if data_inicial:
        queryset = queryset.filter(data_hora__date__gte=data_inicial)
    if data_final:
        queryset = queryset.filter(data_hora__date__lte=data_final)
    return queryset
