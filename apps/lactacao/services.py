from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.rebanho.models import Animal
from apps.reproducao.models import Parto

from .models import Lactacao


def _validar_salvar(lactacao: Lactacao) -> Lactacao:
    lactacao.full_clean()
    lactacao.save()
    return lactacao


@transaction.atomic
def iniciar_lactacao(
    *,
    vaca: Animal,
    data_inicio: date,
    parto: Parto | None = None,
    observacoes: str = "",
) -> Lactacao:
    vaca = Animal.objects.select_for_update().get(pk=vaca.pk)
    if vaca.sexo != Animal.Sexo.FEMEA:
        raise ValidationError({"vaca": _("A lactação só pode pertencer a uma fêmea.")})
    if not vaca.esta_ativo:
        raise ValidationError({"vaca": _("A lactação só pode ser iniciada para vaca ativa.")})
    if parto is None:
        raise ValidationError({"parto": _("Selecione o parto que iniciou esta lactação.")})
    parto = Parto.objects.select_for_update().get(pk=parto.pk)
    if parto.vaca_id != vaca.pk:
        raise ValidationError({"parto": _("O parto pertence a outra vaca.")})
    if parto.situacao == Parto.Situacao.CANCELADO:
        raise ValidationError({"parto": _("Um parto cancelado não pode iniciar lactação.")})
    data_parto = timezone.localtime(parto.data_hora).date()
    if data_inicio < data_parto:
        raise ValidationError({"data_inicio": _("A lactação não pode começar antes do parto.")})
    if (
        Lactacao.objects.select_for_update()
        .filter(vaca=vaca, situacao=Lactacao.Situacao.ATIVA)
        .exists()
    ):
        raise ValidationError({"vaca": _("Esta vaca já possui uma lactação ativa.")})
    maior_ordem = (
        Lactacao.objects.filter(vaca=vaca)
        .exclude(situacao=Lactacao.Situacao.CANCELADA)
        .aggregate(valor=Max("ordem"))["valor"]
        or 0
    )
    lactacao = Lactacao(
        vaca=vaca,
        parto=parto,
        ordem=maior_ordem + 1,
        data_inicio=data_inicio,
        observacoes=observacoes.strip(),
    )
    return _validar_salvar(lactacao)


@transaction.atomic
def secar_lactacao(*, lactacao: Lactacao, data_secagem: date, observacoes: str = "") -> Lactacao:
    lactacao = Lactacao.objects.select_for_update().get(pk=lactacao.pk)
    if lactacao.situacao != Lactacao.Situacao.ATIVA:
        raise ValidationError(_("Somente uma lactação ativa pode ser seca."))
    if data_secagem > timezone.localdate():
        raise ValidationError({"data_secagem": _("A secagem não pode ser futura.")})
    if lactacao.producoes.filter(
        ordenha__ativo_registro=True, ordenha__data__gt=data_secagem
    ).exists():
        raise ValidationError(
            {"data_secagem": _("Há produção registrada depois da data de secagem.")}
        )
    lactacao.data_secagem = data_secagem
    lactacao.situacao = Lactacao.Situacao.SECA
    if observacoes.strip():
        lactacao.observacoes = f"{lactacao.observacoes}\nSecagem: {observacoes.strip()}".strip()
    return _validar_salvar(lactacao)


@transaction.atomic
def encerrar_lactacao(
    *, lactacao: Lactacao, data_encerramento: date, observacoes: str = ""
) -> Lactacao:
    lactacao = Lactacao.objects.select_for_update().get(pk=lactacao.pk)
    if lactacao.situacao in {
        Lactacao.Situacao.ENCERRADA,
        Lactacao.Situacao.CANCELADA,
    }:
        raise ValidationError(_("Esta lactação já está encerrada ou cancelada."))
    if data_encerramento > timezone.localdate():
        raise ValidationError({"data_encerramento": _("O encerramento não pode ser futuro.")})
    if lactacao.data_secagem and data_encerramento < lactacao.data_secagem:
        raise ValidationError(
            {"data_encerramento": _("O encerramento não pode anteceder a secagem.")}
        )
    if lactacao.producoes.filter(
        ordenha__ativo_registro=True, ordenha__data__gt=data_encerramento
    ).exists():
        raise ValidationError(
            {"data_encerramento": _("Há produção registrada depois do encerramento.")}
        )
    lactacao.data_encerramento = data_encerramento
    lactacao.situacao = Lactacao.Situacao.ENCERRADA
    if observacoes.strip():
        lactacao.observacoes = (
            f"{lactacao.observacoes}\nEncerramento: {observacoes.strip()}".strip()
        )
    return _validar_salvar(lactacao)


@transaction.atomic
def cancelar_lactacao(*, lactacao: Lactacao, justificativa: str) -> Lactacao:
    lactacao = Lactacao.objects.select_for_update().get(pk=lactacao.pk)
    if not justificativa.strip():
        raise ValidationError({"justificativa": _("O cancelamento exige justificativa.")})
    if lactacao.producoes.exists():
        raise ValidationError(
            _("Uma lactação com produção registrada não pode ser cancelada; encerre-a.")
        )
    lactacao.situacao = Lactacao.Situacao.CANCELADA
    lactacao.motivo_cancelamento = justificativa.strip()
    return _validar_salvar(lactacao)
