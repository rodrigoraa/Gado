from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import ConfiguracaoSistema

from .models import DestinoLeite, Ordenha, ProducaoAnimal


def _atribuir(instance: Any, dados: Mapping[str, Any], campos: Iterable[str]) -> None:
    for campo in campos:
        if campo in dados:
            setattr(instance, campo, dados[campo])


def _configuracao() -> ConfiguracaoSistema:
    return ConfiguracaoSistema.obter()


def _janela_ordenha(ordenha: Ordenha) -> tuple[datetime, datetime]:
    """Retorna uma janela semiaberta conservadora para avaliar a carencia.

    Sem horario informado nao existe um instante seguro a assumir. Nesse caso,
    qualquer tratamento que sobreponha o dia local da ordenha precisa gerar o
    aviso; escolher o fim do dia produziria falso negativo para leite obtido
    antes de uma liberacao ocorrida no mesmo dia.
    """

    fuso = timezone.get_current_timezone()
    if ordenha.horario is not None:
        momento = timezone.make_aware(
            datetime.combine(ordenha.data, ordenha.horario),
            fuso,
        )
        return momento, momento

    inicio = timezone.make_aware(datetime.combine(ordenha.data, time.min), fuso)
    return inicio, inicio + timedelta(days=1)


@transaction.atomic
def salvar_ordenha(*, instancia: Ordenha | None = None, **dados: Any) -> Ordenha:
    if instancia and not instancia._state.adding:
        ordenha = Ordenha.objects.select_for_update().get(pk=instancia.pk)
        campos_criticos = {"data", "periodo", "quantidade_total", "quantidade_vacas", "lote"}
        alterou = any(
            campo in dados and dados[campo] != getattr(ordenha, campo) for campo in campos_criticos
        )
        if alterou and not dados.get("motivo_correcao"):
            raise ValidationError({"motivo_correcao": "Informe o motivo da correção da ordenha."})
        if alterou:
            dados["situacao"] = Ordenha.Situacao.CORRIGIDA
    else:
        ordenha = Ordenha()

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
    lactacao: Any | None = None,
) -> ProducaoAnimal:
    from apps.lactacao.models import Lactacao
    from apps.rebanho.models import Animal

    vaca = Animal.objects.select_for_update().get(pk=vaca.pk)
    if vaca.situacao != Animal.Situacao.ATIVO:
        raise ValidationError({"vaca": "A produção só pode ser lançada para um animal ativo."})

    if lactacao is None:
        lactacoes = list(
            Lactacao.objects.select_for_update().filter(
                vaca=vaca,
                situacao=Lactacao.Situacao.ATIVA,
            )
        )
        if not lactacoes:
            raise ValidationError({"vaca": "A vaca não possui lactação ativa."})
        if len(lactacoes) > 1:
            raise ValidationError(
                {"vaca": "Há mais de uma lactação ativa; corrija o cadastro antes de lançar."}
            )
        lactacao = lactacoes[0]
    else:
        lactacao = Lactacao.objects.select_for_update().get(pk=lactacao.pk)

    ordenha = Ordenha.objects.select_for_update().get(pk=ordenha.pk)
    if lactacao.vaca_id != vaca.pk:
        raise ValidationError({"lactacao": "A lactação selecionada não pertence à vaca."})
    if lactacao.situacao != Lactacao.Situacao.ATIVA:
        raise ValidationError({"lactacao": "A vaca não possui uma lactação ativa."})
    if ordenha.data < lactacao.data_inicio:
        raise ValidationError({"ordenha": "A ordenha não pode anteceder o início da lactação."})
    limites_finais = [
        data_limite
        for data_limite in (lactacao.data_secagem, lactacao.data_encerramento)
        if data_limite is not None
    ]
    if limites_finais and ordenha.data > min(limites_finais):
        raise ValidationError(
            {"ordenha": "A ordenha não pode ocorrer após o fim efetivo da lactação."}
        )
    producao = ProducaoAnimal(
        ordenha=ordenha,
        vaca=vaca,
        lactacao=lactacao,
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
    justificativa: str,
) -> ProducaoAnimal:
    if not justificativa.strip():
        raise ValidationError({"justificativa": "A correção da produção exige justificativa."})
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
    if (excede_litros or excede_percentual) and not justificativa.strip():
        raise ValidationError(
            {
                "justificativa_divergencia": (
                    "A diferença entre o total e as produções exige justificativa."
                )
            }
        )
    ordenha.justificativa_divergencia = justificativa
    ordenha.save(update_fields=("justificativa_divergencia", "atualizado_em"))
    return ordenha


@transaction.atomic
def cancelar_ordenha(*, ordenha: Ordenha, motivo: str) -> Ordenha:
    if not motivo.strip():
        raise ValidationError({"motivo": "O cancelamento exige justificativa."})
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
        ("data", "ordenha", "tratamento", "tipo", "quantidade_litros", "observacoes"),
    )
    destino.full_clean()
    destino.save()
    return destino


def vaca_em_carencia(
    *, vaca: Any, ordenha: Ordenha | None = None, momento: datetime | None = None
) -> bool:
    from apps.saude.models import Tratamento

    tratamentos = Tratamento.objects.filter(
        animal=vaca,
        ativo_registro=True,
    ).exclude(situacao=Tratamento.Situacao.CANCELADO)
    if momento is not None:
        return tratamentos.filter(
            data_hora__lte=momento,
            data_liberacao__gt=momento,
        ).exists()
    if ordenha is not None:
        inicio, fim = _janela_ordenha(ordenha)
        if inicio == fim:
            return tratamentos.filter(
                data_hora__lte=inicio,
                data_liberacao__gt=inicio,
            ).exists()
        return tratamentos.filter(
            data_hora__lt=fim,
            data_liberacao__gt=inicio,
        ).exists()
    agora = timezone.now()
    return tratamentos.filter(data_hora__lte=agora, data_liberacao__gt=agora).exists()
