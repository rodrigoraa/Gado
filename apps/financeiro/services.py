from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import ConfiguracaoSistema
from apps.core.uploads import (
    DadosUpload,
    capturar_dados_upload,
    desativar_metadados_upload,
    registrar_metadados_upload,
)

from .models import (
    EntregaLeite,
    FechamentoLeite,
    Laticinio,
    PrecoLeite,
    RecebimentoLeite,
    _dinheiro,
)

SITUACOES_ENTREGA_PENDENTE = {
    EntregaLeite.Situacao.REGISTRADA,
    EntregaLeite.Situacao.AGUARDANDO_FECHAMENTO,
}


def _atribuir(instance: Any, dados: Mapping[str, Any], campos: Iterable[str]) -> None:
    for campo in campos:
        if campo in dados:
            setattr(instance, campo, dados[campo])


def _sincronizar_upload(
    *, instancia: Any, campo: str, informado: bool, dados_upload: DadosUpload | None
) -> None:
    arquivo = getattr(instancia, campo)
    if dados_upload:
        registrar_metadados_upload(
            objeto=instancia,
            campo=campo,
            arquivo_salvo=arquivo,
            dados=dados_upload,
        )
    elif informado and not arquivo:
        desativar_metadados_upload(objeto=instancia, campo=campo)


def _somar_mes(ano: int, mes: int, quantidade: int = 1) -> tuple[int, int]:
    indice = ano * 12 + mes - 1 + quantidade
    return indice // 12, indice % 12 + 1


def _data_com_dia(ano: int, mes: int, dia: int) -> date:
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def calcular_data_prevista(*, coleta: datetime, laticinio: Laticinio) -> date:
    coleta_local = timezone.localtime(coleta) if timezone.is_aware(coleta) else coleta
    ano, mes = coleta_local.year, coleta_local.month
    if coleta_local.day > laticinio.dia_fechamento:
        ano, mes = _somar_mes(ano, mes)
    fechamento = _data_com_dia(ano, mes, laticinio.dia_fechamento)
    pagamento = _data_com_dia(ano, mes, laticinio.dia_pagamento)
    if pagamento <= fechamento:
        ano, mes = _somar_mes(ano, mes)
        pagamento = _data_com_dia(ano, mes, laticinio.dia_pagamento)
    return pagamento


@transaction.atomic
def salvar_laticinio(
    *, instancia: Laticinio | None = None, confirmar_troca: bool = False, **dados: Any
) -> Laticinio:
    ativos = Laticinio.objects.select_for_update().filter(ativo=True)
    if instancia and not instancia._state.adding:
        laticinio = Laticinio.objects.select_for_update().get(pk=instancia.pk)
        ativos = ativos.exclude(pk=laticinio.pk)
    else:
        laticinio = Laticinio()

    deseja_ativo = dados.get("ativo", laticinio.ativo)
    laticinios_substituidos = list(ativos) if deseja_ativo else []
    if laticinios_substituidos:
        if not confirmar_troca:
            raise ValidationError(
                {
                    "confirmar_troca": (
                        "Já existe um laticínio ativo. Confirme a troca para continuar."
                    )
                }
            )
        for laticinio_anterior in laticinios_substituidos:
            laticinio_anterior.ativo = False
            laticinio_anterior.save(update_fields=("ativo", "atualizado_em"))

    _atribuir(
        laticinio,
        dados,
        (
            "razao_social",
            "nome_fantasia",
            "cpf_cnpj",
            "telefone",
            "email",
            "endereco",
            "codigo_produtor",
            "dia_fechamento",
            "dia_pagamento",
            "observacoes",
            "ativo",
        ),
    )
    laticinio.full_clean()
    try:
        laticinio.save()
    except IntegrityError as exc:
        raise ValidationError({"ativo": "Já existe um laticínio ativo."}) from exc
    return laticinio


@transaction.atomic
def salvar_preco(*, instancia: PrecoLeite | None = None, **dados: Any) -> PrecoLeite:
    if instancia and not instancia._state.adding:
        preco = PrecoLeite.objects.select_for_update().get(pk=instancia.pk)
        mudou = any(
            campo in dados and dados[campo] != getattr(preco, campo)
            for campo in ("laticinio", "data_inicial", "data_final", "valor_litro")
        )
        if mudou and not str(dados.get("motivo_alteracao", "")).strip():
            raise ValidationError({"motivo_alteracao": "A alteração de preço exige justificativa."})
    else:
        preco = PrecoLeite()
    laticinio = dados.get("laticinio", getattr(preco, "laticinio", None))
    if laticinio:
        # O lock do pai também serializa a primeira faixa, quando ainda não há preço.
        laticinio = Laticinio.objects.select_for_update().get(pk=laticinio.pk)
        dados["laticinio"] = laticinio
        list(
            PrecoLeite.objects.select_for_update()
            .filter(laticinio=laticinio)
            .values_list("pk", flat=True)
        )
    _atribuir(
        preco,
        dados,
        (
            "laticinio",
            "data_inicial",
            "data_final",
            "valor_litro",
            "observacoes",
            "motivo_alteracao",
        ),
    )
    preco.full_clean()
    preco.save()
    return preco


def obter_preco_vigente(*, laticinio: Laticinio, dia: date) -> PrecoLeite | None:
    return (
        PrecoLeite.objects.filter(laticinio=laticinio, data_inicial__lte=dia)
        .filter(Q(data_final__isnull=True) | Q(data_final__gte=dia))
        .order_by("-data_inicial", "-criado_em")
        .first()
    )


@transaction.atomic
def salvar_entrega(*, instancia: EntregaLeite | None = None, **dados: Any) -> EntregaLeite:
    anexo_informado = "anexo" in dados
    dados_upload = capturar_dados_upload(dados.get("anexo")) if anexo_informado else None
    data_original: date | None = None
    if instancia and not instancia._state.adding:
        entrega = EntregaLeite.objects.select_for_update().get(pk=instancia.pk)
        data_original = timezone.localtime(entrega.data_coleta).date()
        if entrega.situacao in {
            EntregaLeite.Situacao.FECHADA,
            EntregaLeite.Situacao.PARCIALMENTE_PAGA,
            EntregaLeite.Situacao.PAGA,
        }:
            raise ValidationError("Uma entrega vinculada a fechamento não pode ser alterada.")
        campos_criticos = {
            "data_coleta",
            "quantidade_litros",
            "valor_litro",
            "bonificacao_qualidade",
            "bonificacao_volume",
            "outras_bonificacoes",
            "desconto_qualidade",
            "frete",
            "taxas",
            "outros_descontos",
        }
        mudou = any(
            campo in dados and dados[campo] != getattr(entrega, campo) for campo in campos_criticos
        )
        if mudou and not str(dados.get("motivo_correcao", "")).strip():
            raise ValidationError({"motivo_correcao": "A correção financeira exige justificativa."})
    else:
        entrega = EntregaLeite()

    laticinio: Laticinio | None = None
    if entrega.laticinio_id:
        laticinio = entrega.laticinio
    else:
        laticinio = Laticinio.objects.select_for_update().filter(ativo=True).first()
        if not laticinio:
            raise ValidationError("Cadastre e ative um laticínio antes de registrar a entrega.")
        entrega.laticinio = laticinio
    if laticinio is None:
        raise ValidationError("Não foi possível determinar o laticínio ativo.")

    coleta = dados.get("data_coleta", getattr(entrega, "data_coleta", timezone.now()))
    coleta_local = timezone.localtime(coleta) if timezone.is_aware(coleta) else coleta
    data_mudou = data_original is not None and coleta_local.date() != data_original
    preco_vigente = obter_preco_vigente(laticinio=laticinio, dia=coleta_local.date())
    preco_recebido = dados.get("valor_litro")
    preco_informado = None if preco_recebido in (None, "") else Decimal(str(preco_recebido))
    preco_inalterado = preco_informado is not None and preco_informado == entrega.valor_litro
    if (
        instancia
        and not instancia._state.adding
        and not data_mudou
        and (preco_informado is None or preco_inalterado)
    ):
        preco_aplicado = entrega.valor_litro
    elif preco_informado is not None:
        preco_aplicado = preco_informado
        if preco_vigente is None or preco_aplicado != preco_vigente.valor_litro:
            if not str(dados.get("justificativa_preco", "")).strip():
                raise ValidationError(
                    {"justificativa_preco": "O preço manual exige justificativa."}
                )
            entrega.preco_manual = True
    elif preco_vigente:
        preco_aplicado = preco_vigente.valor_litro
        entrega.preco_manual = False
    else:
        raise ValidationError({"valor_litro": "Não existe preço vigente para a data da coleta."})

    dados = dict(dados)
    dados["valor_litro"] = preco_aplicado
    dados.setdefault(
        "data_prevista_pagamento", calcular_data_prevista(coleta=coleta, laticinio=laticinio)
    )
    _atribuir(
        entrega,
        dados,
        (
            "data_coleta",
            "quantidade_litros",
            "valor_litro",
            "preco_manual",
            "justificativa_preco",
            "bonificacao_qualidade",
            "bonificacao_volume",
            "outras_bonificacoes",
            "desconto_qualidade",
            "frete",
            "taxas",
            "outros_descontos",
            "data_prevista_pagamento",
            "numero_documento",
            "anexo",
            "observacoes",
            "motivo_correcao",
        ),
    )
    entrega.situacao = EntregaLeite.Situacao.AGUARDANDO_FECHAMENTO
    entrega.full_clean()
    entrega.save()
    _sincronizar_upload(
        instancia=entrega,
        campo="anexo",
        informado=anexo_informado,
        dados_upload=dados_upload,
    )
    return entrega


def _ha_divergencia(fechamento: FechamentoLeite) -> bool:
    configuracao = ConfiguracaoSistema.obter()
    diferencas = fechamento.diferencas
    return abs(diferencas["litros"]) > configuracao.tolerancia_divergencia_litros or any(
        abs(diferencas[chave]) > configuracao.tolerancia_financeira
        for chave in ("valor_bruto", "bonificacoes", "descontos", "valor_liquido")
    )


def _recalcular_fechamento(fechamento: FechamentoLeite) -> FechamentoLeite:
    totais = fechamento.entregas.exclude(situacao=EntregaLeite.Situacao.CANCELADA).aggregate(
        litros=Sum("quantidade_litros"),
        bruto=Sum("valor_bruto"),
        bonificacoes=Sum("total_bonificacoes"),
        descontos=Sum("total_descontos"),
        liquido=Sum("valor_liquido"),
    )
    fechamento.total_litros_calculado = totais["litros"] or Decimal("0.000")
    fechamento.valor_bruto_calculado = _dinheiro(totais["bruto"])
    fechamento.bonificacoes_calculadas = _dinheiro(totais["bonificacoes"])
    fechamento.descontos_calculados = _dinheiro(totais["descontos"])
    fechamento.valor_liquido_calculado = _dinheiro(totais["liquido"])
    return fechamento


def _transicionar_entregas(
    entregas: Iterable[EntregaLeite],
    *,
    situacao: str,
    data_pagamento_integral: date | None = None,
) -> None:
    """Persiste cada transicao para que validacoes de concorrencia e auditoria atuem."""

    for entrega in entregas:
        entrega.situacao = situacao
        entrega.data_pagamento_integral = data_pagamento_integral
        entrega.save(update_fields=("situacao", "data_pagamento_integral", "atualizado_em"))


def _finalizar_fechamento_bloqueado(
    *, fechamento: FechamentoLeite, entregas: list[EntregaLeite]
) -> FechamentoLeite:
    if not entregas:
        raise ValidationError({"entregas": "O fechamento deve possuir ao menos uma entrega."})
    if any(
        not entrega.ativo_registro
        or entrega.situacao not in SITUACOES_ENTREGA_PENDENTE
        or entrega.laticinio_id != fechamento.laticinio_id
        for entrega in entregas
    ):
        raise ValidationError(
            {"entregas": "Há entrega cancelada, já processada ou de outro laticínio."}
        )

    _recalcular_fechamento(fechamento)
    fechamento.situacao = (
        FechamentoLeite.Situacao.DIVERGENTE
        if _ha_divergencia(fechamento)
        else FechamentoLeite.Situacao.FECHADO
    )
    fechamento.full_clean()
    fechamento.save()
    _transicionar_entregas(entregas, situacao=EntregaLeite.Situacao.FECHADA)
    return fechamento


@transaction.atomic
def criar_fechamento(
    *, entregas: Iterable[EntregaLeite], finalizar: bool = True, **dados: Any
) -> FechamentoLeite:
    arquivo_informado = "arquivo_demonstrativo" in dados
    dados_upload = (
        capturar_dados_upload(dados.get("arquivo_demonstrativo")) if arquivo_informado else None
    )
    ids = list(dict.fromkeys(entrega.pk for entrega in entregas))
    if not ids:
        raise ValidationError({"entregas": "Selecione ao menos uma entrega."})
    entregas_bloqueadas = list(
        EntregaLeite.objects.select_for_update()
        .filter(pk__in=ids, ativo_registro=True)
        .exclude(situacao=EntregaLeite.Situacao.CANCELADA)
        .order_by("pk")
    )
    if len(entregas_bloqueadas) != len(ids):
        raise ValidationError({"entregas": "Há entrega inexistente ou cancelada."})
    if any(entrega.situacao not in SITUACOES_ENTREGA_PENDENTE for entrega in entregas_bloqueadas):
        raise ValidationError({"entregas": "Há entrega já processada em outro fluxo."})
    laticinios = {entrega.laticinio_id for entrega in entregas_bloqueadas}
    if len(laticinios) != 1:
        raise ValidationError({"entregas": "Todas as entregas devem ser do mesmo laticínio."})
    laticinio = Laticinio.objects.select_for_update().get(pk=laticinios.pop())
    data_inicial = dados.get("data_inicial")
    data_final = dados.get("data_final")
    if data_inicial and data_final:
        fora_periodo = any(
            not data_inicial <= timezone.localtime(entrega.data_coleta).date() <= data_final
            for entrega in entregas_bloqueadas
        )
        if fora_periodo:
            raise ValidationError(
                {"entregas": "Todas as entregas devem pertencer ao período do fechamento."}
            )
    ja_usadas = FechamentoLeite.objects.filter(entregas__pk__in=ids).exclude(
        situacao=FechamentoLeite.Situacao.CANCELADO
    )
    if ja_usadas.exists():
        raise ValidationError(
            {"entregas": "Uma das entregas já pertence a outro fechamento ativo."}
        )

    fechamento = FechamentoLeite(laticinio=laticinio)
    _atribuir(
        fechamento,
        dados,
        (
            "competencia",
            "data_inicial",
            "data_final",
            "total_litros_informado",
            "valor_bruto_informado",
            "bonificacoes_informadas",
            "descontos_informados",
            "valor_liquido_informado",
            "data_prevista_pagamento",
            "numero_demonstrativo",
            "arquivo_demonstrativo",
            "observacoes",
            "motivo_ajuste",
        ),
    )
    fechamento.full_clean()
    fechamento.save()
    _sincronizar_upload(
        instancia=fechamento,
        campo="arquivo_demonstrativo",
        informado=arquivo_informado,
        dados_upload=dados_upload,
    )
    fechamento.entregas.set(entregas_bloqueadas)
    _recalcular_fechamento(fechamento)
    if finalizar:
        return _finalizar_fechamento_bloqueado(
            fechamento=fechamento,
            entregas=entregas_bloqueadas,
        )
    fechamento.save()
    return fechamento


@transaction.atomic
def finalizar_fechamento(*, fechamento: FechamentoLeite) -> FechamentoLeite:
    fechamento = (
        FechamentoLeite.objects.select_for_update()
        .select_related("laticinio")
        .get(pk=fechamento.pk)
    )
    if fechamento.situacao != FechamentoLeite.Situacao.ABERTO:
        raise ValidationError("Somente um fechamento em aberto pode ser finalizado.")
    entregas = list(
        EntregaLeite.objects.select_for_update().filter(fechamentos=fechamento).order_by("pk")
    )
    return _finalizar_fechamento_bloqueado(
        fechamento=fechamento,
        entregas=entregas,
    )


@transaction.atomic
def atualizar_dados_informados(*, fechamento: FechamentoLeite, **dados: Any) -> FechamentoLeite:
    arquivo_informado = "arquivo_demonstrativo" in dados
    dados_upload = (
        capturar_dados_upload(dados.get("arquivo_demonstrativo")) if arquivo_informado else None
    )
    fechamento = FechamentoLeite.objects.select_for_update().get(pk=fechamento.pk)
    campos_financeiros = {
        "total_litros_informado",
        "valor_bruto_informado",
        "bonificacoes_informadas",
        "descontos_informados",
        "valor_liquido_informado",
    }
    alterou_valor = any(
        campo in dados and dados[campo] != getattr(fechamento, campo)
        for campo in campos_financeiros
    )
    if alterou_valor and not str(dados.get("motivo_ajuste", "")).strip():
        raise ValidationError({"motivo_ajuste": "O ajuste financeiro exige justificativa."})
    _atribuir(
        fechamento,
        dados,
        (
            "total_litros_informado",
            "valor_bruto_informado",
            "bonificacoes_informadas",
            "descontos_informados",
            "valor_liquido_informado",
            "numero_demonstrativo",
            "arquivo_demonstrativo",
            "observacoes",
            "motivo_ajuste",
        ),
    )
    _recalcular_fechamento(fechamento)
    divergente = _ha_divergencia(fechamento)
    if not divergente and fechamento.situacao == FechamentoLeite.Situacao.DIVERGENTE:
        fechamento.situacao = FechamentoLeite.Situacao.FECHADO
    elif divergente:
        fechamento.situacao = FechamentoLeite.Situacao.DIVERGENTE
    fechamento.full_clean()
    fechamento.save()
    _sincronizar_upload(
        instancia=fechamento,
        campo="arquivo_demonstrativo",
        informado=arquivo_informado,
        dados_upload=dados_upload,
    )
    return fechamento


def _atualizar_situacao_pagamento(
    fechamento: FechamentoLeite, data_pagamento: date | None = None
) -> None:
    total = fechamento.total_recebido
    tolerancia = ConfiguracaoSistema.obter().tolerancia_financeira
    if total <= 0:
        fechamento.situacao = (
            FechamentoLeite.Situacao.DIVERGENTE
            if _ha_divergencia(fechamento)
            else FechamentoLeite.Situacao.FECHADO
        )
        situacao_entrega = EntregaLeite.Situacao.FECHADA
    elif total + tolerancia >= fechamento.valor_liquido_calculado:
        fechamento.situacao = FechamentoLeite.Situacao.PAGO
        situacao_entrega = EntregaLeite.Situacao.PAGA
    else:
        fechamento.situacao = FechamentoLeite.Situacao.PARCIALMENTE_PAGO
        situacao_entrega = EntregaLeite.Situacao.PARCIALMENTE_PAGA
    fechamento.save(update_fields=("situacao", "atualizado_em"))
    entregas = list(
        EntregaLeite.objects.select_for_update().filter(fechamentos=fechamento).order_by("pk")
    )
    data_integral = (
        data_pagamento or timezone.localdate()
        if situacao_entrega == EntregaLeite.Situacao.PAGA
        else None
    )
    _transicionar_entregas(
        entregas,
        situacao=situacao_entrega,
        data_pagamento_integral=data_integral,
    )


@transaction.atomic
def registrar_recebimento(**dados: Any) -> RecebimentoLeite:
    anexo_informado = "anexo" in dados
    dados_upload = capturar_dados_upload(dados.get("anexo")) if anexo_informado else None
    fechamento_original = dados.get("fechamento")
    if not fechamento_original:
        raise ValidationError({"fechamento": "Informe o fechamento."})
    fechamento = FechamentoLeite.objects.select_for_update().get(pk=fechamento_original.pk)
    if fechamento.situacao == FechamentoLeite.Situacao.ABERTO:
        raise ValidationError({"fechamento": "Finalize o fechamento antes de receber."})
    list(fechamento.recebimentos.select_for_update().values_list("pk", flat=True))
    valor = Decimal(dados.get("valor") or 0)
    total_apos = fechamento.total_recebido + valor
    if (
        total_apos > fechamento.valor_liquido_calculado
        and not str(dados.get("justificativa_excesso", "")).strip()
    ):
        raise ValidationError({"justificativa_excesso": "O valor excedente exige justificativa."})
    recebimento = RecebimentoLeite(fechamento=fechamento)
    _atribuir(
        recebimento,
        dados,
        (
            "data",
            "valor",
            "forma_pagamento",
            "referencia",
            "anexo",
            "observacoes",
            "justificativa_excesso",
        ),
    )
    recebimento.full_clean()
    recebimento.save()
    _sincronizar_upload(
        instancia=recebimento,
        campo="anexo",
        informado=anexo_informado,
        dados_upload=dados_upload,
    )
    _atualizar_situacao_pagamento(fechamento, recebimento.data)
    return recebimento


@transaction.atomic
def cancelar_recebimento(*, recebimento: RecebimentoLeite, motivo: str) -> RecebimentoLeite:
    if not motivo.strip():
        raise ValidationError({"motivo": "O cancelamento exige justificativa."})
    recebimento = (
        RecebimentoLeite.objects.select_for_update()
        .select_related("fechamento")
        .get(pk=recebimento.pk)
    )
    fechamento = FechamentoLeite.objects.select_for_update().get(pk=recebimento.fechamento_id)
    recebimento.situacao = RecebimentoLeite.Situacao.CANCELADO
    recebimento.motivo_cancelamento = motivo
    recebimento.ativo_registro = False
    recebimento.cancelado_em = timezone.now()
    recebimento.full_clean()
    recebimento.save()
    _atualizar_situacao_pagamento(fechamento)
    return recebimento


@transaction.atomic
def cancelar_fechamento(*, fechamento: FechamentoLeite, motivo: str) -> FechamentoLeite:
    if not motivo.strip():
        raise ValidationError({"motivo": "O cancelamento exige justificativa."})
    fechamento = FechamentoLeite.objects.select_for_update().get(pk=fechamento.pk)
    if fechamento.recebimentos.filter(situacao=RecebimentoLeite.Situacao.CONFIRMADO).exists():
        raise ValidationError("Cancele os recebimentos confirmados antes de cancelar o fechamento.")
    entregas = list(
        EntregaLeite.objects.select_for_update().filter(fechamentos=fechamento).order_by("pk")
    )
    fechamento.situacao = FechamentoLeite.Situacao.CANCELADO
    fechamento.motivo_cancelamento = motivo
    fechamento.ativo_registro = False
    fechamento.cancelado_em = timezone.now()
    fechamento.full_clean()
    fechamento.save()
    _transicionar_entregas(
        entregas,
        situacao=EntregaLeite.Situacao.AGUARDANDO_FECHAMENTO,
    )
    return fechamento


@transaction.atomic
def cancelar_entrega(*, entrega: EntregaLeite, motivo: str) -> EntregaLeite:
    if not motivo.strip():
        raise ValidationError({"motivo": "O cancelamento exige justificativa."})
    entrega = EntregaLeite.objects.select_for_update().get(pk=entrega.pk)
    if entrega.fechamentos.exclude(situacao=FechamentoLeite.Situacao.CANCELADO).exists():
        raise ValidationError("Cancele o fechamento antes de cancelar esta entrega.")
    entrega.situacao = EntregaLeite.Situacao.CANCELADA
    entrega.motivo_cancelamento = motivo
    entrega.ativo_registro = False
    entrega.cancelado_em = timezone.now()
    entrega.full_clean()
    entrega.save()
    return entrega
