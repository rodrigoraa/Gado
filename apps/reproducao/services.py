from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.uploads import capturar_dados_upload, registrar_metadados_upload
from apps.rebanho.models import Animal

from .models import (
    Cobertura,
    DiagnosticoGestacao,
    HistoricoCobertura,
    HistoricoParto,
    Nascimento,
    Parto,
    PerdaGestacional,
    parametros_gestacao,
)

TRATAMENTO_SUBSTITUIR = "substituir"
TRATAMENTO_MANTER = "manter"
TRATAMENTO_INCERTA = "incerta"
REGISTRO_AUTOMATICO = "Alteração registrada automaticamente pelo sistema."
TRATAMENTOS_COBERTURA_ABERTA = {
    TRATAMENTO_SUBSTITUIR,
    TRATAMENTO_MANTER,
    TRATAMENTO_INCERTA,
}


def _validar_salvar(instancia: Any) -> Any:
    instancia.full_clean()
    instancia.save()
    return instancia


def _registrar_historico_cobertura(
    *,
    cobertura: Cobertura,
    evento: str,
    situacao_anterior: str = "",
    situacao_nova: str = "",
    previsao_anterior: date | None = None,
    previsao_nova: date | None = None,
    justificativa: str = "",
) -> HistoricoCobertura:
    historico = HistoricoCobertura(
        cobertura=cobertura,
        evento=evento,
        situacao_anterior=situacao_anterior,
        situacao_nova=situacao_nova,
        previsao_anterior=previsao_anterior,
        previsao_nova=previsao_nova,
        justificativa=justificativa.strip(),
    )
    return _validar_salvar(historico)


def _alterar_situacao_cobertura(
    cobertura: Cobertura, nova_situacao: str, *, evento: str, justificativa: str = ""
) -> Cobertura:
    anterior = cobertura.situacao
    cobertura.situacao = nova_situacao
    if nova_situacao == Cobertura.Situacao.CANCELADA:
        cobertura.motivo_cancelamento = justificativa.strip()
    _validar_salvar(cobertura)
    _registrar_historico_cobertura(
        cobertura=cobertura,
        evento=evento,
        situacao_anterior=anterior,
        situacao_nova=nova_situacao,
        justificativa=justificativa,
    )
    return cobertura


@transaction.atomic
def registrar_cobertura(
    *,
    vaca: Animal,
    data_cobertura: date,
    tipo: str,
    forma_identificacao: str,
    touro: Animal | None = None,
    observacoes: str = "",
    tratamento_cobertura_aberta: str = TRATAMENTO_SUBSTITUIR,
    justificativa_substituicao: str = "Nova cobertura registrada.",
) -> Cobertura:
    vaca = Animal.objects.select_for_update().get(pk=vaca.pk)
    if touro is not None:
        touro = Animal.objects.select_for_update().get(pk=touro.pk)
    if tratamento_cobertura_aberta not in TRATAMENTOS_COBERTURA_ABERTA:
        raise ValidationError(
            {
                "tratamento_cobertura_aberta": _(
                    "Escolha substituir, manter ou marcar a anterior como incerta."
                )
            }
        )

    abertas = list(
        Cobertura.objects.select_for_update()
        .filter(vaca=vaca, situacao__in=Cobertura.SITUACOES_ABERTAS)
        .order_by("-data", "-criado_em")
    )
    if abertas and tratamento_cobertura_aberta != TRATAMENTO_MANTER:
        nova_situacao = (
            Cobertura.Situacao.SUBSTITUIDA
            if tratamento_cobertura_aberta == TRATAMENTO_SUBSTITUIR
            else Cobertura.Situacao.INCERTA
        )
        for anterior in abertas:
            _alterar_situacao_cobertura(
                anterior,
                nova_situacao,
                evento="NOVA_COBERTURA",
                justificativa=justificativa_substituicao,
            )

    cobertura = Cobertura(
        vaca=vaca,
        touro=touro,
        data=data_cobertura,
        tipo=tipo,
        forma_identificacao=forma_identificacao,
        observacoes=observacoes.strip(),
    )
    _validar_salvar(cobertura)
    _registrar_historico_cobertura(
        cobertura=cobertura,
        evento="CRIACAO",
        situacao_nova=cobertura.situacao,
        previsao_nova=cobertura.previsao_atual_parto,
    )
    return cobertura


@transaction.atomic
def alterar_data_cobertura(
    *, cobertura: Cobertura, nova_data: date, justificativa: str = ""
) -> Cobertura:
    cobertura = Cobertura.objects.select_for_update().get(pk=cobertura.pk)
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    if cobertura.situacao in {
        Cobertura.Situacao.FINALIZADA_COM_PARTO,
        Cobertura.Situacao.CANCELADA,
    }:
        raise ValidationError(_("Uma cobertura finalizada ou cancelada não pode ser alterada."))

    data_anterior = cobertura.data
    previsao_anterior = cobertura.previsao_atual_parto
    dias, _margem = parametros_gestacao()
    cobertura.data = nova_data
    cobertura.previsao_atual_parto = nova_data + timedelta(days=dias)
    cobertura.motivo_alteracao = justificativa.strip()
    _validar_salvar(cobertura)
    _registrar_historico_cobertura(
        cobertura=cobertura,
        evento="ALTERACAO_DATA",
        previsao_anterior=previsao_anterior,
        previsao_nova=cobertura.previsao_atual_parto,
        justificativa=f"Data: {data_anterior:%d/%m/%Y} → {nova_data:%d/%m/%Y}. {justificativa}",
    )
    return cobertura


@transaction.atomic
def cancelar_cobertura(*, cobertura: Cobertura, justificativa: str = "") -> Cobertura:
    cobertura = Cobertura.objects.select_for_update().get(pk=cobertura.pk)
    if cobertura.situacao == Cobertura.Situacao.FINALIZADA_COM_PARTO:
        raise ValidationError(_("Cancele ou corrija primeiro o parto relacionado."))
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    return _alterar_situacao_cobertura(
        cobertura,
        Cobertura.Situacao.CANCELADA,
        evento="CANCELAMENTO",
        justificativa=justificativa,
    )


@transaction.atomic
def registrar_diagnostico(
    *,
    cobertura: Cobertura,
    data_diagnostico: date,
    resultado: str,
    metodo: str,
    responsavel: str = "",
    idade_gestacional_estimada_dias: int | None = None,
    nova_previsao_parto: date | None = None,
    observacoes: str = "",
) -> DiagnosticoGestacao:
    cobertura = Cobertura.objects.select_for_update().select_related("vaca").get(pk=cobertura.pk)
    if not cobertura.esta_aberta:
        raise ValidationError({"cobertura": _("Esta cobertura já está encerrada.")})
    diagnostico = DiagnosticoGestacao(
        vaca=cobertura.vaca,
        cobertura=cobertura,
        data=data_diagnostico,
        resultado=resultado,
        metodo=metodo,
        responsavel=responsavel.strip(),
        idade_gestacional_estimada_dias=idade_gestacional_estimada_dias,
        nova_previsao_parto=nova_previsao_parto,
        observacoes=observacoes.strip(),
    )
    _validar_salvar(diagnostico)

    anterior = cobertura.situacao
    previsao_anterior = cobertura.previsao_atual_parto
    if resultado == DiagnosticoGestacao.Resultado.PRENHE:
        cobertura.situacao = Cobertura.Situacao.PRENHEZ_CONFIRMADA
    elif resultado == DiagnosticoGestacao.Resultado.VAZIA:
        cobertura.situacao = Cobertura.Situacao.NAO_EMPRENHOU
    else:
        cobertura.situacao = Cobertura.Situacao.AGUARDANDO_CONFIRMACAO
    if nova_previsao_parto:
        cobertura.previsao_atual_parto = nova_previsao_parto
    _validar_salvar(cobertura)
    _registrar_historico_cobertura(
        cobertura=cobertura,
        evento="DIAGNOSTICO",
        situacao_anterior=anterior,
        situacao_nova=cobertura.situacao,
        previsao_anterior=previsao_anterior,
        previsao_nova=cobertura.previsao_atual_parto,
        justificativa=f"{diagnostico.get_resultado_display()} — {observacoes}".strip(" —"),
    )
    return diagnostico


@transaction.atomic
def registrar_perda_gestacional(
    *,
    cobertura: Cobertura,
    data_perda: date,
    tipo: str,
    responsavel: str = "",
    observacoes: str = "",
) -> PerdaGestacional:
    cobertura = Cobertura.objects.select_for_update().select_related("vaca").get(pk=cobertura.pk)
    if not cobertura.esta_aberta:
        raise ValidationError({"cobertura": _("Esta cobertura já está encerrada.")})
    perda = PerdaGestacional(
        vaca=cobertura.vaca,
        cobertura=cobertura,
        data=data_perda,
        tipo=tipo,
        responsavel=responsavel.strip(),
        observacoes=observacoes.strip(),
    )
    _validar_salvar(perda)
    nova_situacao = (
        Cobertura.Situacao.INCERTA
        if tipo == PerdaGestacional.Tipo.SUSPEITA
        else Cobertura.Situacao.PERDA_GESTACIONAL
    )
    _alterar_situacao_cobertura(
        cobertura,
        nova_situacao,
        evento="PERDA_GESTACIONAL",
        justificativa=f"{perda.get_tipo_display()} — {observacoes}".strip(" —"),
    )
    return perda


def _normalizar_data_hora(valor: datetime) -> datetime:
    if timezone.is_naive(valor):
        return timezone.make_aware(valor, timezone.get_current_timezone())
    return valor


@transaction.atomic
def registrar_parto(
    *,
    vaca: Animal,
    data_hora: datetime,
    resultado: str,
    bezerros: Iterable[dict[str, Any]] | None = None,
    cobertura: Cobertura | None = None,
    quantidade_bezerros: int | None = None,
    necessitou_auxilio: bool = False,
    responsavel: str = "",
    observacoes: str = "",
) -> Parto:
    """Registra parto, crias, filiação e cobertura numa só transação."""

    vaca = Animal.objects.select_for_update().get(pk=vaca.pk)
    if not vaca.esta_ativo:
        raise ValidationError({"vaca": _("O parto só pode ser registrado para uma vaca ativa.")})
    if cobertura is not None:
        cobertura = (
            Cobertura.objects.select_for_update(of=("self",))
            .select_related("touro")
            .get(pk=cobertura.pk)
        )
        if cobertura.vaca_id != vaca.pk:
            raise ValidationError({"cobertura": _("A cobertura pertence a outra vaca.")})
        if (
            Parto.objects.filter(cobertura=cobertura)
            .exclude(situacao=Parto.Situacao.CANCELADO)
            .exists()
        ):
            raise ValidationError({"cobertura": _("Esta cobertura já possui um parto ativo.")})
        if not cobertura.esta_aberta:
            raise ValidationError({"cobertura": _("Esta cobertura já está encerrada.")})

    dados_bezerros = list(bezerros or [])
    quantidade = quantidade_bezerros
    if quantidade is None:
        quantidade = len(dados_bezerros)
    if quantidade != len(dados_bezerros):
        raise ValidationError(
            {
                "quantidade_bezerros": _(
                    "A quantidade informada deve coincidir com os bezerros cadastrados."
                )
            }
        )
    data_hora = _normalizar_data_hora(data_hora)
    parto = Parto(
        vaca=vaca,
        cobertura=cobertura,
        data_hora=data_hora,
        resultado=resultado,
        quantidade_bezerros=quantidade,
        necessitou_auxilio=necessitou_auxilio,
        responsavel=responsavel.strip(),
        observacoes=observacoes.strip(),
    )
    _validar_salvar(parto)

    data_nascimento = timezone.localtime(data_hora).date()
    pai = cobertura.touro if cobertura else None
    for dados in dados_bezerros:
        dados_upload_foto = capturar_dados_upload(dados.get("foto"))
        situacao_nascimento = dados.get("situacao", Nascimento.Situacao.VIVO)
        esta_vivo = situacao_nascimento == Nascimento.Situacao.VIVO
        peso = dados.get("peso_ao_nascer_kg", dados.get("peso_ao_nascer"))
        animal = Animal(
            identificacao=dados.get("identificacao"),
            identificacao_provisoria=dados.get("identificacao_provisoria"),
            nome=dados.get("nome", ""),
            cor=dados.get("cor", ""),
            sexo=dados.get("sexo", ""),
            tipo_animal=Animal.TipoAnimal.BEZERRO,
            data_nascimento=data_nascimento,
            data_nascimento_aproximada=False,
            raca=dados.get("raca"),
            mae=vaca,
            pai=pai,
            origem=Animal.Origem.NASCIDO_SITIO,
            data_entrada=data_nascimento,
            situacao=Animal.Situacao.ATIVO if esta_vivo else Animal.Situacao.MORTO,
            data_saida=None if esta_vivo else data_nascimento,
            motivo_saida="" if esta_vivo else str(_("Óbito relacionado ao nascimento")),
            peso_atual=peso,
            foto=dados.get("foto"),
            observacoes=dados.get("observacoes", ""),
        )
        _validar_salvar(animal)
        if dados_upload_foto:
            registrar_metadados_upload(
                objeto=animal,
                campo="foto",
                arquivo_salvo=animal.foto,
                dados=dados_upload_foto,
            )
        nascimento = Nascimento(
            parto=parto,
            animal=animal,
            situacao=situacao_nascimento,
            peso_ao_nascer_kg=peso,
            observacoes=dados.get("observacoes", ""),
        )
        _validar_salvar(nascimento)

    if cobertura is not None:
        _alterar_situacao_cobertura(
            cobertura,
            Cobertura.Situacao.FINALIZADA_COM_PARTO,
            evento="PARTO",
            justificativa=f"Parto {parto.pk}",
        )

    return parto


def _dados_parto(parto: Parto) -> dict[str, Any]:
    return {
        "data_hora": parto.data_hora.isoformat(),
        "resultado": parto.resultado,
        "quantidade_bezerros": parto.quantidade_bezerros,
        "necessitou_auxilio": parto.necessitou_auxilio,
        "responsavel": parto.responsavel,
        "observacoes": parto.observacoes,
        "situacao": parto.situacao,
    }


@transaction.atomic
def corrigir_parto(*, parto: Parto, justificativa: str = "", **alteracoes: Any) -> Parto:
    parto = (
        Parto.objects.select_for_update(of=("self",))
        .select_related("vaca", "cobertura")
        .prefetch_related("nascimentos__animal")
        .get(pk=parto.pk)
    )
    if parto.situacao == Parto.Situacao.CANCELADO:
        raise ValidationError(_("Um parto cancelado não pode ser corrigido."))
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    permitidos = {
        "data_hora",
        "resultado",
        "necessitou_auxilio",
        "responsavel",
        "observacoes",
    }
    anteriores = _dados_parto(parto)
    data_anterior = parto.data_hora
    for campo, valor in alteracoes.items():
        if campo in permitidos:
            setattr(parto, campo, valor)
    parto.data_hora = _normalizar_data_hora(parto.data_hora)
    data_anterior_local = timezone.localtime(_normalizar_data_hora(data_anterior)).date()
    nova_data = timezone.localtime(parto.data_hora).date()

    nascimentos = list(
        Nascimento.objects.select_for_update().select_related("animal").filter(parto=parto)
    )
    animais = {
        animal.pk: animal
        for animal in Animal.objects.select_for_update().filter(
            pk__in=[nascimento.animal_id for nascimento in nascimentos]
        )
    }
    if nova_data != data_anterior_local:
        for nascimento in nascimentos:
            animal = animais[nascimento.animal_id]
            if animal.movimentacoes_lote.filter(data__lt=nova_data).exists():
                raise ValidationError(
                    {"data_hora": _("Há movimentação de cria anterior à nova data do parto.")}
                )
            if animal.pesagens.filter(data__lt=nova_data).exists():
                raise ValidationError(
                    {"data_hora": _("Há pesagem de cria anterior à nova data do parto.")}
                )
            if (
                animal.data_entrada
                and animal.data_entrada < nova_data
                and animal.data_entrada != data_anterior_local
            ):
                raise ValidationError(
                    {"data_hora": _("A entrada de uma cria antecederia a nova data do parto.")}
                )
            if (
                animal.data_saida
                and animal.data_saida < nova_data
                and animal.data_saida != data_anterior_local
            ):
                raise ValidationError(
                    {"data_hora": _("A saída de uma cria antecederia a nova data do parto.")}
                )

    parto.situacao = Parto.Situacao.CORRIGIDO
    parto.motivo_correcao = justificativa.strip()
    _validar_salvar(parto)

    if nova_data != data_anterior_local:
        for nascimento in nascimentos:
            animal = animais[nascimento.animal_id]
            animal.data_nascimento = nova_data
            if animal.data_entrada == data_anterior_local:
                animal.data_entrada = nova_data
            if animal.data_saida == data_anterior_local:
                animal.data_saida = nova_data
            _validar_salvar(animal)

    historico = HistoricoParto(
        parto=parto,
        evento="CORRECAO",
        dados_anteriores=anteriores,
        dados_novos=_dados_parto(parto),
        justificativa=justificativa.strip(),
    )
    _validar_salvar(historico)
    return parto


@transaction.atomic
def cancelar_parto(*, parto: Parto, justificativa: str = "") -> Parto:
    parto = (
        Parto.objects.select_for_update(of=("self",)).select_related("cobertura").get(pk=parto.pk)
    )
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    if parto.situacao == Parto.Situacao.CANCELADO:
        raise ValidationError(_("Este parto já está cancelado."))
    if Nascimento.objects.select_for_update().filter(parto=parto).exists():
        raise ValidationError(
            _(
                "O parto possui nascimentos vinculados e não pode ser cancelado. "
                "Use a correção para preservar a filiação e o histórico."
            )
        )
    anteriores = _dados_parto(parto)
    parto.situacao = Parto.Situacao.CANCELADO
    parto.motivo_cancelamento = justificativa.strip()
    _validar_salvar(parto)
    historico = HistoricoParto(
        parto=parto,
        evento="CANCELAMENTO",
        dados_anteriores=anteriores,
        dados_novos=_dados_parto(parto),
        justificativa=justificativa.strip(),
    )
    _validar_salvar(historico)

    cobertura = parto.cobertura
    if cobertura is not None and cobertura.situacao == Cobertura.Situacao.FINALIZADA_COM_PARTO:
        tem_positivo = cobertura.diagnosticos.filter(
            resultado=DiagnosticoGestacao.Resultado.PRENHE
        ).exists()
        _alterar_situacao_cobertura(
            cobertura,
            (
                Cobertura.Situacao.PRENHEZ_CONFIRMADA
                if tem_positivo
                else Cobertura.Situacao.AGUARDANDO_CONFIRMACAO
            ),
            evento="CANCELAMENTO_PARTO",
            justificativa=justificativa,
        )
    return parto
