from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedUUIDModel
from apps.rebanho.models import Animal, ExclusaoFisicaProtegidaMixin
from apps.reproducao.models import Parto


class Lactacao(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Situacao(models.TextChoices):
        ATIVA = "ATIVA", _("Ativa")
        SECA = "SECA", _("Seca")
        ENCERRADA = "ENCERRADA", _("Encerrada")
        CANCELADA = "CANCELADA", _("Cancelada")

    vaca = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="lactacoes")
    parto = models.OneToOneField(
        Parto,
        on_delete=models.PROTECT,
        related_name="lactacao",
        null=True,
        blank=True,
    )
    ordem = models.PositiveSmallIntegerField(_("ordem da lactação"))
    data_inicio = models.DateField(_("data de início"))
    data_encerramento = models.DateField(_("data de encerramento"), null=True, blank=True)
    data_secagem = models.DateField(_("data de secagem"), null=True, blank=True)
    situacao = models.CharField(
        _("situação"),
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.ATIVA,
    )
    observacoes = models.TextField(_("observações"), blank=True)
    motivo_cancelamento = models.TextField(_("motivo do cancelamento"), blank=True)

    class Meta:
        verbose_name = _("lactação")
        verbose_name_plural = _("lactações")
        ordering = ("-data_inicio", "-criado_em")
        indexes = [
            models.Index(
                fields=("vaca", "situacao", "-data_inicio"),
                name="lact_lact_vaca_sit_data_idx",
            ),
            models.Index(fields=("situacao", "data_inicio"), name="lact_lact_sit_inicio_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("vaca",),
                condition=Q(situacao="ATIVA"),
                name="lact_lact_ativa_vaca_unica",
            ),
            models.UniqueConstraint(
                fields=("vaca", "ordem"),
                condition=~Q(situacao="CANCELADA"),
                name="lact_lact_ordem_vaca_unica",
            ),
            models.CheckConstraint(condition=Q(ordem__gte=1), name="lact_lact_ordem_positiva"),
            models.CheckConstraint(
                condition=Q(data_encerramento__isnull=True)
                | Q(data_encerramento__gte=models.F("data_inicio")),
                name="lact_lact_fim_apos_inicio",
            ),
            models.CheckConstraint(
                condition=Q(data_secagem__isnull=True)
                | Q(data_secagem__gte=models.F("data_inicio")),
                name="lact_lact_secagem_apos_inicio",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ordem}ª lactação de {self.vaca}"

    @property
    def ordem_lactacao(self) -> int:
        return self.ordem

    @property
    def esta_ativa(self) -> bool:
        return self.situacao == self.Situacao.ATIVA

    @property
    def data_referencia_fim(self) -> date:
        if self.data_secagem:
            return self.data_secagem
        if self.data_encerramento:
            return self.data_encerramento
        return timezone.localdate()

    @property
    def dias_em_lactacao(self) -> int:
        return max((self.data_referencia_fim - self.data_inicio).days, 0)

    @property
    def producao_acumulada(self) -> Decimal:
        from .selectors import indicadores_lactacao

        return indicadores_lactacao(lactacao=self).producao_acumulada

    @property
    def media_diaria(self) -> Decimal:
        from .selectors import indicadores_lactacao

        return indicadores_lactacao(lactacao=self).media_diaria

    @property
    def producao_ultimos_sete_dias(self) -> Decimal:
        from .selectors import indicadores_lactacao

        return indicadores_lactacao(lactacao=self).producao_ultimos_sete_dias

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        hoje = timezone.localdate()
        if self.vaca_id:
            if self.vaca.sexo != Animal.Sexo.FEMEA:
                erros["vaca"] = _("A lactação só pode pertencer a uma fêmea.")
            if not self.vaca.esta_ativo and self.situacao == self.Situacao.ATIVA:
                erros["vaca"] = _("Não é possível iniciar lactação para animal inativo.")
        if self.data_inicio and self.data_inicio > hoje:
            erros["data_inicio"] = _("A data de início não pode ser futura.")
        if self.parto_id:
            if self.vaca_id and self.parto.vaca_id != self.vaca_id:
                erros["parto"] = _("O parto pertence a outra vaca.")
            data_parto = timezone.localtime(self.parto.data_hora).date()
            if self.data_inicio and self.data_inicio < data_parto:
                erros["data_inicio"] = _("A lactação não pode começar antes do parto.")
            if self.parto.situacao == Parto.Situacao.CANCELADO:
                erros["parto"] = _("Um parto cancelado não pode iniciar lactação.")
        if self.data_secagem and self.data_secagem < self.data_inicio:
            erros["data_secagem"] = _("A secagem não pode anteceder o início.")
        if self.data_encerramento and self.data_encerramento < self.data_inicio:
            erros["data_encerramento"] = _("O encerramento não pode anteceder o início.")
        if (
            self.data_secagem
            and self.data_encerramento
            and self.data_encerramento < self.data_secagem
        ):
            erros["data_encerramento"] = _("O encerramento não pode anteceder a secagem.")
        if self.situacao == self.Situacao.ATIVA and (self.data_secagem or self.data_encerramento):
            erros["situacao"] = _("Uma lactação ativa não pode estar seca ou encerrada.")
        if self.situacao == self.Situacao.SECA and not self.data_secagem:
            erros["data_secagem"] = _("Informe a data de secagem.")
        if self.situacao == self.Situacao.ENCERRADA and not self.data_encerramento:
            erros["data_encerramento"] = _("Informe a data de encerramento.")
        if self.situacao == self.Situacao.CANCELADA and not self.motivo_cancelamento.strip():
            erros["motivo_cancelamento"] = _("O cancelamento exige uma justificativa.")
        if erros:
            raise ValidationError(erros)
