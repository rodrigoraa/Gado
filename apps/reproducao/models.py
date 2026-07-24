from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import ConfiguracaoSistema, TimeStampedUUIDModel
from apps.rebanho.models import Animal, ExclusaoFisicaProtegidaMixin


def parametros_gestacao() -> tuple[int, int]:
    try:
        configuracao = ConfiguracaoSistema.obter()
        return int(configuracao.gestacao_dias), int(configuracao.margem_parto_dias)
    except Exception:
        return (
            int(getattr(settings, "GESTACAO_DIAS", 283)),
            int(getattr(settings, "MARGEM_PARTO_DIAS", 7)),
        )


class Cobertura(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Tipo(models.TextChoices):
        MONTA_NATURAL = "MONTA_NATURAL", _("Monta natural")
        INSEMINACAO = "INSEMINACAO", _("Inseminação")

    class FormaIdentificacao(models.TextChoices):
        OBSERVADA = "OBSERVADA", _("Observada")
        ESTIMADA = "ESTIMADA", _("Estimada")
        INFORMADA = "INFORMADA", _("Informada")

    class Situacao(models.TextChoices):
        REGISTRADA = "REGISTRADA", _("Registrada")
        AGUARDANDO_CONFIRMACAO = "AGUARDANDO_CONFIRMACAO", _("Aguardando confirmação")
        PRENHEZ_CONFIRMADA = "PRENHEZ_CONFIRMADA", _("Prenhez confirmada")
        NAO_EMPRENHOU = "NAO_EMPRENHOU", _("Não emprenhou")
        SUBSTITUIDA = "SUBSTITUIDA", _("Substituída por nova cobertura")
        INCERTA = "INCERTA", _("Situação incerta")
        PERDA_GESTACIONAL = "PERDA_GESTACIONAL", _("Perda gestacional")
        FINALIZADA_COM_PARTO = "FINALIZADA_COM_PARTO", _("Finalizada com parto")
        CANCELADA = "CANCELADA", _("Cancelada")

    SITUACOES_ABERTAS = {
        Situacao.REGISTRADA,
        Situacao.AGUARDANDO_CONFIRMACAO,
        Situacao.PRENHEZ_CONFIRMADA,
        Situacao.INCERTA,
    }

    vaca = models.ForeignKey(
        Animal,
        verbose_name=_("vaca"),
        on_delete=models.PROTECT,
        related_name="coberturas",
    )
    touro = models.ForeignKey(
        Animal,
        verbose_name=_("touro"),
        on_delete=models.PROTECT,
        related_name="coberturas_como_touro",
        null=True,
        blank=True,
    )
    data = models.DateField(_("data"))
    data_original = models.DateField(_("data original"), editable=False, null=True)
    tipo = models.CharField(_("tipo"), max_length=20, choices=Tipo.choices)
    forma_identificacao = models.CharField(
        _("forma de identificação"),
        max_length=20,
        choices=FormaIdentificacao.choices,
        default=FormaIdentificacao.OBSERVADA,
    )
    situacao = models.CharField(
        _("situação"),
        max_length=30,
        choices=Situacao.choices,
        default=Situacao.REGISTRADA,
    )
    previsao_original_parto = models.DateField(
        _("previsão original do parto"), null=True, blank=True, editable=False
    )
    previsao_atual_parto = models.DateField(_("previsão atual do parto"), null=True, blank=True)
    observacoes = models.TextField(_("observações"), blank=True)
    motivo_alteracao = models.TextField(_("motivo da alteração"), blank=True)
    motivo_cancelamento = models.TextField(_("motivo do cancelamento"), blank=True)

    class Meta:
        verbose_name = _("cobertura")
        verbose_name_plural = _("coberturas")
        ordering = ("-data", "-criado_em")
        indexes = [
            models.Index(
                fields=("vaca", "situacao", "-data"),
                name="repro_cob_vaca_sit_data_idx",
            ),
            models.Index(
                fields=("previsao_atual_parto", "situacao"),
                name="repro_cob_prev_sit_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.vaca} — {self.get_tipo_display()} em {self.data:%d/%m/%Y}"

    @property
    def esta_aberta(self) -> bool:
        return self.situacao in self.SITUACOES_ABERTAS

    @property
    def intervalo_provavel(self) -> tuple[object, object] | None:
        if not self.previsao_atual_parto:
            return None
        _, margem = parametros_gestacao()
        return (
            self.previsao_atual_parto - timedelta(days=margem),
            self.previsao_atual_parto + timedelta(days=margem),
        )

    @property
    def inicio_intervalo_parto(self):  # type: ignore[no-untyped-def]
        intervalo = self.intervalo_provavel
        return intervalo[0] if intervalo else None

    @property
    def fim_intervalo_parto(self):  # type: ignore[no-untyped-def]
        intervalo = self.intervalo_provavel
        return intervalo[1] if intervalo else None

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        hoje = timezone.localdate()
        if self.vaca_id:
            if self.vaca.sexo != Animal.Sexo.FEMEA:
                erros["vaca"] = _("A cobertura só pode ser registrada para uma fêmea.")
            elif not self.vaca.esta_ativo:
                erros["vaca"] = _("A cobertura só pode ser registrada para uma fêmea ativa.")
            elif self.data and self.vaca.eh_bezerro_em(self.data):
                erros["vaca"] = _("Uma bezerra ainda não pode receber cobertura.")
            if self.data and self.vaca.data_nascimento and self.data < self.vaca.data_nascimento:
                erros["data"] = _("A cobertura não pode anteceder o nascimento da vaca.")
        if self.touro_id:
            if self.touro.sexo != Animal.Sexo.MACHO:
                erros["touro"] = _("O reprodutor deve ser um macho.")
            elif not self.touro.esta_ativo:
                erros["touro"] = _("O reprodutor deve estar ativo.")
            elif self.data and self.touro.eh_bezerro_em(self.data):
                erros["touro"] = _("Um bezerro macho ainda não pode ser usado em coberturas.")
        if self.data and self.data > hoje:
            erros["data"] = _("A data da cobertura não pode ser futura.")
        if self.situacao == self.Situacao.CANCELADA and not self.motivo_cancelamento.strip():
            erros["motivo_cancelamento"] = _("O cancelamento exige uma justificativa.")
        if (
            self.data_original
            and self.data != self.data_original
            and not self.motivo_alteracao.strip()
        ):
            erros["motivo_alteracao"] = _("Justifique a alteração da data original.")
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        dias, _margem = parametros_gestacao()
        if self.data_original is None:
            self.data_original = self.data
        if self.previsao_original_parto is None:
            self.previsao_original_parto = self.data_original + timedelta(days=dias)
        if self.previsao_atual_parto is None:
            self.previsao_atual_parto = self.previsao_original_parto
        return super().save(*args, **kwargs)


class DiagnosticoGestacao(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Resultado(models.TextChoices):
        PRENHE = "PRENHE", _("Prenhe")
        VAZIA = "VAZIA", _("Vazia")
        INCONCLUSIVO = "INCONCLUSIVO", _("Inconclusivo")

    class Metodo(models.TextChoices):
        PALPACAO = "PALPACAO", _("Palpação")
        ULTRASSOM = "ULTRASSOM", _("Ultrassom")
        EXAME_LABORATORIAL = "EXAME_LABORATORIAL", _("Exame laboratorial")
        OBSERVACAO = "OBSERVACAO", _("Observação")
        OUTRO = "OUTRO", _("Outro")

    vaca = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="diagnosticos_gestacao",
    )
    cobertura = models.ForeignKey(Cobertura, on_delete=models.PROTECT, related_name="diagnosticos")
    data = models.DateField(_("data"), default=timezone.localdate)
    resultado = models.CharField(_("resultado"), max_length=20, choices=Resultado.choices)
    metodo = models.CharField(_("método"), max_length=30, choices=Metodo.choices)
    responsavel = models.CharField(_("responsável"), max_length=150, blank=True)
    idade_gestacional_estimada_dias = models.PositiveIntegerField(
        _("idade gestacional estimada (dias)"), null=True, blank=True
    )
    nova_previsao_parto = models.DateField(_("nova previsão do parto"), null=True, blank=True)
    observacoes = models.TextField(_("observações"), blank=True)

    class Meta:
        verbose_name = _("diagnóstico de gestação")
        verbose_name_plural = _("diagnósticos de gestação")
        ordering = ("-data", "-criado_em")
        indexes = [
            models.Index(fields=("cobertura", "-data"), name="repro_diag_cob_data_idx"),
            models.Index(
                fields=("vaca", "resultado", "-data"),
                name="repro_diag_vaca_res_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.vaca} — {self.get_resultado_display()} em {self.data:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        if self.data and self.data > timezone.localdate():
            erros["data"] = _("A data do diagnóstico não pode ser futura.")
        if self.cobertura_id:
            if self.vaca_id and self.vaca_id != self.cobertura.vaca_id:
                erros["vaca"] = _("A vaca deve ser a mesma da cobertura.")
            if self.data and self.data < self.cobertura.data:
                erros["data"] = _("O diagnóstico não pode anteceder a cobertura.")
        if self.nova_previsao_parto and self.nova_previsao_parto < self.data:
            erros["nova_previsao_parto"] = _("A previsão deve ser posterior ao diagnóstico.")
        if erros:
            raise ValidationError(erros)


class PerdaGestacional(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Tipo(models.TextChoices):
        ABORTO = "ABORTO", _("Aborto")
        PERDA_GESTACIONAL = "PERDA_GESTACIONAL", _("Perda gestacional")
        REABSORCAO = "REABSORCAO", _("Reabsorção")
        SUSPEITA = "SUSPEITA", _("Suspeita")

    vaca = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="perdas_gestacionais")
    cobertura = models.ForeignKey(
        Cobertura, on_delete=models.PROTECT, related_name="perdas_gestacionais"
    )
    data = models.DateField(_("data"), default=timezone.localdate)
    tipo = models.CharField(_("tipo"), max_length=30, choices=Tipo.choices)
    responsavel = models.CharField(_("responsável"), max_length=150, blank=True)
    observacoes = models.TextField(_("observações"), blank=True)

    class Meta:
        verbose_name = _("perda gestacional")
        verbose_name_plural = _("perdas gestacionais")
        ordering = ("-data", "-criado_em")
        indexes = [models.Index(fields=("vaca", "-data"), name="repro_perda_vaca_data_idx")]

    def __str__(self) -> str:
        return f"{self.vaca} — {self.get_tipo_display()} em {self.data:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        if self.data and self.data > timezone.localdate():
            erros["data"] = _("A data da perda não pode ser futura.")
        if self.cobertura_id:
            if self.vaca_id and self.vaca_id != self.cobertura.vaca_id:
                erros["vaca"] = _("A vaca deve ser a mesma da cobertura.")
            if self.data and self.data < self.cobertura.data:
                erros["data"] = _("A perda não pode anteceder a cobertura.")
        if erros:
            raise ValidationError(erros)


class Parto(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Resultado(models.TextChoices):
        NORMAL = "NORMAL", _("Normal")
        COM_AUXILIO = "COM_AUXILIO", _("Com auxílio")
        CESAREA = "CESAREA", _("Cesárea")
        ABORTO = "ABORTO", _("Aborto")
        NATIMORTO = "NATIMORTO", _("Natimorto")
        OUTRO = "OUTRO", _("Outro")

    class Situacao(models.TextChoices):
        REGISTRADO = "REGISTRADO", _("Registrado")
        CORRIGIDO = "CORRIGIDO", _("Corrigido")
        CANCELADO = "CANCELADO", _("Cancelado")

    vaca = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="partos")
    cobertura = models.ForeignKey(
        Cobertura,
        on_delete=models.PROTECT,
        related_name="partos",
        null=True,
        blank=True,
    )
    data_hora = models.DateTimeField(_("data e hora"), default=timezone.now)
    resultado = models.CharField(_("resultado"), max_length=20, choices=Resultado.choices)
    quantidade_bezerros = models.PositiveSmallIntegerField(_("quantidade de bezerros"), default=1)
    necessitou_auxilio = models.BooleanField(_("necessitou auxílio"), default=False)
    responsavel = models.CharField(_("responsável"), max_length=150, blank=True)
    observacoes = models.TextField(_("observações"), blank=True)
    situacao = models.CharField(
        _("situação"),
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.REGISTRADO,
    )
    motivo_correcao = models.TextField(_("motivo da correção"), blank=True)
    motivo_cancelamento = models.TextField(_("motivo do cancelamento"), blank=True)

    class Meta:
        verbose_name = _("parto")
        verbose_name_plural = _("partos")
        ordering = ("-data_hora", "-criado_em")
        indexes = [
            models.Index(fields=("vaca", "-data_hora"), name="repro_parto_vaca_data_idx"),
            models.Index(fields=("situacao", "-data_hora"), name="repro_parto_sit_data_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("cobertura",),
                condition=Q(cobertura__isnull=False) & ~Q(situacao="CANCELADO"),
                name="repro_parto_ativo_cob_unico",
            ),
            models.CheckConstraint(
                condition=Q(quantidade_bezerros__gte=0),
                name="repro_parto_qtd_nao_negativa",
            ),
        ]

    def __str__(self) -> str:
        return f"Parto de {self.vaca} em {timezone.localtime(self.data_hora):%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        momento = self.data_hora
        if momento and timezone.is_naive(momento) and settings.USE_TZ:
            momento = timezone.make_aware(momento, timezone.get_current_timezone())
        if momento and momento > timezone.now():
            erros["data_hora"] = _("A data e hora do parto não pode ser futura.")
        if self.vaca_id and momento:
            data_local = (
                timezone.localtime(momento).date() if timezone.is_aware(momento) else momento.date()
            )
            if self.vaca.data_nascimento and data_local < self.vaca.data_nascimento:
                erros["data_hora"] = _("O parto não pode anteceder o nascimento da vaca.")
            if self.vaca.sexo != Animal.Sexo.FEMEA:
                erros["vaca"] = _("O parto só pode ser associado a uma fêmea.")
        if self.cobertura_id:
            if self.vaca_id and self.cobertura.vaca_id != self.vaca_id:
                erros["cobertura"] = _("A cobertura pertence a outra vaca.")
            if momento and momento.date() < self.cobertura.data:
                erros["data_hora"] = _("O parto não pode anteceder a cobertura.")
        if self.resultado != self.Resultado.ABORTO and self.quantidade_bezerros < 1:
            erros["quantidade_bezerros"] = _("Informe ao menos um bezerro.")
        if self.situacao == self.Situacao.CORRIGIDO and not self.motivo_correcao.strip():
            erros["motivo_correcao"] = _("A correção exige uma justificativa.")
        if self.situacao == self.Situacao.CANCELADO and not self.motivo_cancelamento.strip():
            erros["motivo_cancelamento"] = _("O cancelamento exige uma justificativa.")
        if erros:
            raise ValidationError(erros)


class Nascimento(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Situacao(models.TextChoices):
        VIVO = "VIVO", _("Vivo")
        NATIMORTO = "NATIMORTO", _("Natimorto")
        MORREU_APOS_NASCIMENTO = "MORREU_APOS_NASCIMENTO", _("Morreu após nascimento")

    parto = models.ForeignKey(Parto, on_delete=models.PROTECT, related_name="nascimentos")
    animal = models.OneToOneField(Animal, on_delete=models.PROTECT, related_name="nascimento")
    situacao = models.CharField(
        _("situação"), max_length=30, choices=Situacao.choices, default=Situacao.VIVO
    )
    peso_ao_nascer_kg = models.DecimalField(
        _("peso ao nascer (kg)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    observacoes = models.TextField(_("observações"), blank=True)

    class Meta:
        verbose_name = _("nascimento")
        verbose_name_plural = _("nascimentos")
        ordering = ("parto", "criado_em")
        constraints = [
            models.CheckConstraint(
                condition=Q(peso_ao_nascer_kg__isnull=True) | Q(peso_ao_nascer_kg__gt=0),
                name="repro_nascimento_peso_pos",
            )
        ]

    def __str__(self) -> str:
        return f"Nascimento de {self.animal}"

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        if self.parto_id and self.animal_id:
            if self.animal.mae_id != self.parto.vaca_id:
                erros["animal"] = _("A mãe do bezerro deve ser a vaca do parto.")
            data_parto = timezone.localtime(self.parto.data_hora).date()
            if self.animal.data_nascimento != data_parto:
                erros["animal"] = _("O nascimento do animal deve coincidir com o parto.")
        if erros:
            raise ValidationError(erros)


class HistoricoCobertura(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    cobertura = models.ForeignKey(Cobertura, on_delete=models.PROTECT, related_name="historico")
    evento = models.CharField(_("evento"), max_length=50)
    situacao_anterior = models.CharField(max_length=30, blank=True)
    situacao_nova = models.CharField(max_length=30, blank=True)
    previsao_anterior = models.DateField(null=True, blank=True)
    previsao_nova = models.DateField(null=True, blank=True)
    justificativa = models.TextField(_("justificativa"), blank=True)

    class Meta:
        verbose_name = _("histórico de cobertura")
        verbose_name_plural = _("históricos de cobertura")
        ordering = ("-criado_em",)
        indexes = [models.Index(fields=("cobertura", "-criado_em"), name="repro_hist_cob_data_idx")]

    def __str__(self) -> str:
        return f"{self.cobertura}: {self.evento}"


class HistoricoParto(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    parto = models.ForeignKey(Parto, on_delete=models.PROTECT, related_name="historico")
    evento = models.CharField(_("evento"), max_length=30)
    dados_anteriores = models.JSONField(default=dict, blank=True)
    dados_novos = models.JSONField(default=dict, blank=True)
    justificativa = models.TextField(_("justificativa"))

    class Meta:
        verbose_name = _("histórico de parto")
        verbose_name_plural = _("históricos de parto")
        ordering = ("-criado_em",)
        indexes = [models.Index(fields=("parto", "-criado_em"), name="repro_hist_parto_data_idx")]

    def __str__(self) -> str:
        return f"{self.parto}: {self.evento}"
