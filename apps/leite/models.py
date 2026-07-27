from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import SoftDeleteModel, TimeStampedUUIDModel


class Ordenha(TimeStampedUUIDModel, SoftDeleteModel):
    class Periodo(models.TextChoices):
        MANHA = "MANHA", "Matutino"
        TARDE = "TARDE", "Vespertino"
        NOITE = "NOITE", "Noite"
        OUTRO = "OUTRO", "2 Turnos"

    class Modo(models.TextChoices):
        TOTAL = "TOTAL", "Somente total"
        INDIVIDUAL = "INDIVIDUAL", "Por vaca"

    class Situacao(models.TextChoices):
        REGISTRADA = "REGISTRADA", "Registrada"
        CORRIGIDA = "CORRIGIDA", "Corrigida"
        CANCELADA = "CANCELADA", "Cancelada"

    data = models.DateField("data", default=timezone.localdate)
    periodo = models.CharField("turno", max_length=10, choices=Periodo.choices)
    horario = models.TimeField("horário", blank=True, null=True)
    lote = models.ForeignKey(
        "rebanho.Lote",
        verbose_name="lote",
        related_name="ordenhas",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    modo = models.CharField(
        "modo de registro", max_length=12, choices=Modo.choices, default=Modo.TOTAL
    )
    quantidade_total = models.DecimalField(
        "quantidade total (L)",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantidade_vacas = models.PositiveIntegerField("quantidade de vacas", default=0)
    responsavel = models.CharField("responsável", max_length=150, blank=True)
    observacoes = models.TextField("observações", blank=True)
    situacao = models.CharField(
        "situação", max_length=12, choices=Situacao.choices, default=Situacao.REGISTRADA
    )
    duplicidade_confirmada = models.BooleanField(
        "duplicidade de período confirmada",
        default=False,
        help_text="Registra que outra ordenha no mesmo período foi conscientemente mantida.",
    )
    justificativa_divergencia = models.TextField("justificativa da divergência", blank=True)
    motivo_correcao = models.TextField("motivo da correção", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        ordering = ("-data", "periodo", "horario")
        verbose_name = "ordenha"
        verbose_name_plural = "ordenhas"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade_total__gte=0),
                name="leite_ordenha_quantidade_nao_negativa",
            ),
        ]
        indexes = [
            models.Index(fields=("data", "periodo"), name="leite_ord_data_periodo_idx"),
            models.Index(fields=("situacao", "data"), name="leite_ord_situacao_data_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_periodo_display()} de {self.data:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data and self.data > timezone.localdate():
            errors["data"] = "A data da ordenha não pode estar no futuro."
        if self.quantidade_total == 0 and not (self.observacoes or self.motivo_correcao):
            errors["quantidade_total"] = (
                "Informe uma justificativa para uma ordenha com quantidade zero."
            )
        if self.situacao == self.Situacao.CORRIGIDA and not self.motivo_correcao:
            errors["motivo_correcao"] = "A correção exige uma justificativa."
        if self.situacao == self.Situacao.CANCELADA and not self.motivo_cancelamento:
            errors["motivo_cancelamento"] = "O cancelamento exige uma justificativa."
        if self.data and self.periodo:
            registros_do_dia = (
                type(self)
                .objects.filter(
                    data=self.data,
                    ativo_registro=True,
                )
                .exclude(pk=self.pk)
            )
            if self.periodo == self.Periodo.OUTRO and registros_do_dia.exists():
                errors["periodo"] = (
                    "O total de 2 Turnos não pode ser registrado junto com "
                    "outro turno no mesmo dia."
                )
            elif (
                self.periodo in {self.Periodo.MANHA, self.Periodo.TARDE}
                and registros_do_dia.filter(periodo=self.Periodo.OUTRO).exists()
            ):
                errors["periodo"] = (
                    "Já existe o total de 2 Turnos neste dia. Edite esse registro se necessário."
                )
            elif (
                not self.duplicidade_confirmada
                and registros_do_dia.filter(periodo=self.periodo).exists()
            ):
                errors["periodo"] = "Já existe um registro para este turno na data informada."
        if errors:
            raise ValidationError(errors)

    @property
    def total_individual(self) -> Decimal:
        if not self.pk:
            return Decimal("0.000")
        return self.producoes.aggregate(total=Sum("quantidade_litros"))["total"] or Decimal("0.000")

    @property
    def diferenca_individual(self) -> Decimal:
        return (self.quantidade_total or Decimal("0")) - self.total_individual

    @property
    def diferenca_percentual(self) -> Decimal:
        if not self.quantidade_total:
            return Decimal("0.00")
        return (abs(self.diferenca_individual) / self.quantidade_total * Decimal("100")).quantize(
            Decimal("0.01")
        )


class ProducaoAnimal(TimeStampedUUIDModel):
    ordenha = models.ForeignKey(
        Ordenha, verbose_name="ordenha", related_name="producoes", on_delete=models.PROTECT
    )
    vaca = models.ForeignKey(
        "rebanho.Animal",
        verbose_name="vaca",
        related_name="producoes_leite",
        on_delete=models.PROTECT,
    )
    quantidade_litros = models.DecimalField(
        "quantidade (L)",
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ("ordenha__data", "vaca__identificacao")
        verbose_name = "produção individual"
        verbose_name_plural = "produções individuais"
        constraints = [
            models.UniqueConstraint(
                fields=("ordenha", "vaca"), name="leite_producao_ordenha_vaca_unica"
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade_litros__gte=0),
                name="leite_producao_quantidade_nao_negativa",
            ),
        ]
        indexes = [
            models.Index(fields=("vaca", "ordenha"), name="leite_prod_vaca_ord_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.vaca} — {self.quantidade_litros} L"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.ordenha_id and self.ordenha.situacao == Ordenha.Situacao.CANCELADA:
            errors["ordenha"] = "Não é possível lançar produção em uma ordenha cancelada."
        if self.vaca_id:
            sexo = getattr(self.vaca, "sexo", None)
            if sexo != "F":
                errors["vaca"] = "A produção individual só pode ser registrada para uma fêmea."
        if errors:
            raise ValidationError(errors)


class DestinoLeite(TimeStampedUUIDModel):
    class Tipo(models.TextChoices):
        LATICINIO = "LATICINIO", "Laticínio"
        CONSUMO = "CONSUMO", "Consumo próprio"
        BEZERROS = "BEZERROS", "Bezerros"
        QUEIJO = "QUEIJO", "Queijo"
        DERIVADOS = "DERIVADOS", "Outros derivados"
        ARMAZENAMENTO = "ARMAZENAMENTO", "Armazenamento"
        DESCARTE = "DESCARTE", "Descarte"
        PERDA = "PERDA", "Perda"
        OUTRO = "OUTRO", "Outro"

    data = models.DateField("data", default=timezone.localdate)
    ordenha = models.ForeignKey(
        Ordenha,
        verbose_name="ordenha",
        related_name="destinos",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    tipo = models.CharField("tipo", max_length=16, choices=Tipo.choices)
    quantidade_litros = models.DecimalField(
        "quantidade (L)",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ("-data", "tipo")
        verbose_name = "destino do leite"
        verbose_name_plural = "destinos do leite"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade_litros__gte=0),
                name="leite_destino_quantidade_nao_negativa",
            ),
        ]
        indexes = [
            models.Index(fields=("data", "tipo"), name="leite_dest_data_tipo_idx"),
            models.Index(fields=("ordenha",), name="leite_dest_ordenha_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} — {self.quantidade_litros} L em {self.data:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data and self.data > timezone.localdate():
            errors["data"] = "A data do destino não pode estar no futuro."
        if errors:
            raise ValidationError(errors)
