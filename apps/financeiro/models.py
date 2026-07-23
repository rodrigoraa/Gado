from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import SoftDeleteModel, TimeStampedUUIDModel

from .validators import validar_anexo, validar_cpf_cnpj

CENTAVOS = Decimal("0.01")


def _dinheiro(valor: Decimal | None) -> Decimal:
    return (valor or Decimal("0")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def caminho_anexo_entrega(instance: EntregaLeite, filename: str) -> str:
    return f"financeiro/entregas/{instance.id}/{Path(filename).name}"


def caminho_demonstrativo(instance: FechamentoLeite, filename: str) -> str:
    return f"financeiro/fechamentos/{instance.id}/{Path(filename).name}"


def caminho_anexo_recebimento(instance: RecebimentoLeite, filename: str) -> str:
    return f"financeiro/recebimentos/{instance.id}/{Path(filename).name}"


class Laticinio(TimeStampedUUIDModel):
    razao_social = models.CharField("razão social", max_length=200)
    nome_fantasia = models.CharField("nome fantasia", max_length=200, blank=True)
    cpf_cnpj = models.CharField(
        "CNPJ ou CPF", max_length=18, blank=True, validators=[validar_cpf_cnpj]
    )
    telefone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    endereco = models.TextField("endereço", blank=True)
    codigo_produtor = models.CharField("código do produtor", max_length=80, blank=True)
    dia_fechamento = models.PositiveSmallIntegerField(
        "dia habitual de fechamento",
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        default=30,
    )
    dia_pagamento = models.PositiveSmallIntegerField(
        "dia habitual de pagamento",
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        default=10,
    )
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ("-ativo", "razao_social")
        verbose_name = "laticínio"
        verbose_name_plural = "laticínios"
        constraints = [
            models.UniqueConstraint(
                fields=("ativo",),
                condition=Q(ativo=True),
                name="financeiro_apenas_um_laticinio_ativo",
            )
        ]
        indexes = [models.Index(fields=("ativo",), name="financeiro_lat_ativo_idx")]

    def __str__(self) -> str:
        return self.nome_fantasia or self.razao_social

    def validate_constraints(self, exclude=None) -> None:  # type: ignore[no-untyped-def]
        # A troca precisa primeiro desativar o cadastro anterior. O serviço faz isso
        # sob lock e o banco mantém a garantia final contra concorrência.
        return None


class PrecoLeite(TimeStampedUUIDModel):
    laticinio = models.ForeignKey(
        Laticinio, verbose_name="laticínio", related_name="precos", on_delete=models.PROTECT
    )
    data_inicial = models.DateField("data inicial")
    data_final = models.DateField("data final", blank=True, null=True)
    valor_litro = models.DecimalField(
        "valor por litro",
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    observacoes = models.TextField("observações", blank=True)
    motivo_alteracao = models.TextField("motivo da alteração", blank=True)

    class Meta:
        ordering = ("-data_inicial", "-criado_em")
        verbose_name = "preço do leite"
        verbose_name_plural = "histórico de preços do leite"
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_litro__gte=0), name="financeiro_preco_valor_nao_negativo"
            ),
            models.CheckConstraint(
                condition=Q(data_final__isnull=True) | Q(data_final__gte=models.F("data_inicial")),
                name="financeiro_preco_periodo_valido",
            ),
        ]
        indexes = [
            models.Index(
                fields=("laticinio", "data_inicial", "data_final"), name="fin_preco_vigencia_idx"
            )
        ]

    def __str__(self) -> str:
        fim = self.data_final.strftime("%d/%m/%Y") if self.data_final else "em aberto"
        return f"{self.laticinio}: R$ {self.valor_litro}/L ({self.data_inicial:%d/%m/%Y} a {fim})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data_final and self.data_inicial and self.data_final < self.data_inicial:
            errors["data_final"] = "A data final não pode ser anterior à data inicial."
        if self.laticinio_id and self.data_inicial:
            limite_final = self.data_final or date.max
            sobreposto = (
                type(self)
                .objects.filter(laticinio_id=self.laticinio_id, data_inicial__lte=limite_final)
                .filter(Q(data_final__isnull=True) | Q(data_final__gte=self.data_inicial))
                .exclude(pk=self.pk)
            )
            if sobreposto.exists():
                errors["data_inicial"] = "O período se sobrepõe a outro preço deste laticínio."
        if errors:
            raise ValidationError(errors)


class EntregaLeite(TimeStampedUUIDModel, SoftDeleteModel):
    class Situacao(models.TextChoices):
        REGISTRADA = "REGISTRADA", "Registrada"
        AGUARDANDO_FECHAMENTO = "AGUARDANDO_FECHAMENTO", "Aguardando fechamento"
        FECHADA = "FECHADA", "Fechada"
        PARCIALMENTE_PAGA = "PARCIALMENTE_PAGA", "Parcialmente paga"
        PAGA = "PAGA", "Paga"
        CANCELADA = "CANCELADA", "Cancelada"

    laticinio = models.ForeignKey(
        Laticinio, verbose_name="laticínio", related_name="entregas", on_delete=models.PROTECT
    )
    data_coleta = models.DateTimeField("data e hora da coleta", default=timezone.now)
    quantidade_litros = models.DecimalField(
        "quantidade (L)",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    valor_litro = models.DecimalField(
        "valor por litro",
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    preco_manual = models.BooleanField("preço informado manualmente", default=False)
    justificativa_preco = models.TextField("justificativa do preço manual", blank=True)
    valor_bruto = models.DecimalField(
        "valor bruto", max_digits=14, decimal_places=2, default=0, editable=False
    )
    bonificacao_qualidade = models.DecimalField(
        "bonificação por qualidade",
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    bonificacao_volume = models.DecimalField(
        "bonificação por volume",
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    outras_bonificacoes = models.DecimalField(
        "outras bonificações",
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    desconto_qualidade = models.DecimalField(
        "desconto por qualidade",
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    frete = models.DecimalField(
        "frete", max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    taxas = models.DecimalField(
        "taxas", max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    outros_descontos = models.DecimalField(
        "outros descontos",
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    total_bonificacoes = models.DecimalField(
        "total de bonificações", max_digits=14, decimal_places=2, default=0, editable=False
    )
    total_descontos = models.DecimalField(
        "total de descontos", max_digits=14, decimal_places=2, default=0, editable=False
    )
    valor_liquido = models.DecimalField(
        "valor líquido", max_digits=14, decimal_places=2, default=0, editable=False
    )
    situacao = models.CharField(
        "situação", max_length=24, choices=Situacao.choices, default=Situacao.AGUARDANDO_FECHAMENTO
    )
    data_prevista_pagamento = models.DateField("data prevista de pagamento", blank=True, null=True)
    data_pagamento_integral = models.DateField("data do pagamento integral", blank=True, null=True)
    numero_documento = models.CharField("nota ou romaneio", max_length=100, blank=True)
    anexo = models.FileField(
        "anexo", upload_to=caminho_anexo_entrega, validators=[validar_anexo], blank=True
    )
    observacoes = models.TextField("observações", blank=True)
    motivo_correcao = models.TextField("motivo da correção", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        ordering = ("-data_coleta", "-criado_em")
        verbose_name = "entrega de leite"
        verbose_name_plural = "entregas de leite"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantidade_litros__gt=0), name="financeiro_entrega_quantidade_positiva"
            ),
            models.CheckConstraint(
                condition=Q(valor_litro__gte=0), name="financeiro_entrega_preco_nao_negativo"
            ),
        ]
        indexes = [
            models.Index(fields=("laticinio", "data_coleta"), name="fin_entrega_lat_data_idx"),
            models.Index(fields=("situacao", "data_coleta"), name="fin_entrega_sit_data_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.quantidade_litros} L em {timezone.localtime(self.data_coleta):%d/%m/%Y %H:%M}"
        )

    def calcular_totais(self) -> None:
        self.valor_bruto = _dinheiro(
            (self.quantidade_litros or Decimal("0")) * (self.valor_litro or Decimal("0"))
        )
        self.total_bonificacoes = _dinheiro(
            (self.bonificacao_qualidade or Decimal("0"))
            + (self.bonificacao_volume or Decimal("0"))
            + (self.outras_bonificacoes or Decimal("0"))
        )
        self.total_descontos = _dinheiro(
            (self.desconto_qualidade or Decimal("0"))
            + (self.frete or Decimal("0"))
            + (self.taxas or Decimal("0"))
            + (self.outros_descontos or Decimal("0"))
        )
        self.valor_liquido = _dinheiro(
            self.valor_bruto + self.total_bonificacoes - self.total_descontos
        )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data_coleta and self.data_coleta > timezone.now():
            errors["data_coleta"] = "A coleta não pode estar no futuro."
        if self.preco_manual and not self.justificativa_preco.strip():
            errors["justificativa_preco"] = "O preço manual exige uma justificativa."
        if self.situacao == self.Situacao.CANCELADA and not self.motivo_cancelamento.strip():
            errors["motivo_cancelamento"] = "O cancelamento exige uma justificativa."
        if self.situacao == self.Situacao.REGISTRADA and self.motivo_correcao:
            self.situacao = self.Situacao.AGUARDANDO_FECHAMENTO
        if errors:
            raise ValidationError(errors)
        self.calcular_totais()

    def save(self, *args: object, **kwargs: object) -> None:
        self.calcular_totais()
        super().save(*args, **kwargs)


class FechamentoLeite(TimeStampedUUIDModel, SoftDeleteModel):
    class Situacao(models.TextChoices):
        ABERTO = "ABERTO", "Em aberto"
        FECHADO = "FECHADO", "Fechado"
        PARCIALMENTE_PAGO = "PARCIALMENTE_PAGO", "Parcialmente pago"
        PAGO = "PAGO", "Pago"
        DIVERGENTE = "DIVERGENTE", "Divergente"
        CANCELADO = "CANCELADO", "Cancelado"

    laticinio = models.ForeignKey(
        Laticinio, verbose_name="laticínio", related_name="fechamentos", on_delete=models.PROTECT
    )
    competencia = models.DateField("competência", help_text="Use o primeiro dia do mês.")
    data_inicial = models.DateField("data inicial")
    data_final = models.DateField("data final")
    entregas = models.ManyToManyField(
        EntregaLeite, verbose_name="entregas", related_name="fechamentos", blank=True
    )
    total_litros_calculado = models.DecimalField(
        "litros calculados", max_digits=14, decimal_places=3, default=0, editable=False
    )
    valor_bruto_calculado = models.DecimalField(
        "valor bruto calculado", max_digits=14, decimal_places=2, default=0, editable=False
    )
    bonificacoes_calculadas = models.DecimalField(
        "bonificações calculadas", max_digits=14, decimal_places=2, default=0, editable=False
    )
    descontos_calculados = models.DecimalField(
        "descontos calculados", max_digits=14, decimal_places=2, default=0, editable=False
    )
    valor_liquido_calculado = models.DecimalField(
        "valor líquido calculado", max_digits=14, decimal_places=2, default=0, editable=False
    )
    total_litros_informado = models.DecimalField(
        "litros informados",
        max_digits=14,
        decimal_places=3,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
    )
    valor_bruto_informado = models.DecimalField(
        "valor bruto informado", max_digits=14, decimal_places=2, blank=True, null=True
    )
    bonificacoes_informadas = models.DecimalField(
        "bonificações informadas", max_digits=14, decimal_places=2, blank=True, null=True
    )
    descontos_informados = models.DecimalField(
        "descontos informados", max_digits=14, decimal_places=2, blank=True, null=True
    )
    valor_liquido_informado = models.DecimalField(
        "valor líquido informado", max_digits=14, decimal_places=2, blank=True, null=True
    )
    data_prevista_pagamento = models.DateField("data prevista de pagamento", blank=True, null=True)
    situacao = models.CharField(
        "situação", max_length=20, choices=Situacao.choices, default=Situacao.ABERTO
    )
    numero_demonstrativo = models.CharField("número do demonstrativo", max_length=100, blank=True)
    arquivo_demonstrativo = models.FileField(
        "arquivo do demonstrativo",
        upload_to=caminho_demonstrativo,
        validators=[validar_anexo],
        blank=True,
    )
    observacoes = models.TextField("observações", blank=True)
    motivo_ajuste = models.TextField("motivo do ajuste", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        ordering = ("-competencia", "-criado_em")
        verbose_name = "fechamento de leite"
        verbose_name_plural = "fechamentos de leite"
        constraints = [
            models.CheckConstraint(
                condition=Q(data_final__gte=models.F("data_inicial")),
                name="financeiro_fechamento_periodo_valido",
            ),
            models.UniqueConstraint(
                fields=("laticinio", "competencia"),
                condition=~Q(situacao="CANCELADO"),
                name="financeiro_fechamento_competencia_unica",
            ),
        ]
        indexes = [
            models.Index(fields=("laticinio", "competencia"), name="fin_fech_lat_comp_idx"),
            models.Index(
                fields=("situacao", "data_prevista_pagamento"), name="fin_fech_sit_pag_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.laticinio} — {self.competencia:%m/%Y}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data_inicial and self.data_final and self.data_final < self.data_inicial:
            errors["data_final"] = "A data final não pode ser anterior à data inicial."
        if self.competencia and self.competencia.day != 1:
            errors["competencia"] = "A competência deve usar o primeiro dia do mês."
        if self.situacao == self.Situacao.CANCELADO and not self.motivo_cancelamento.strip():
            errors["motivo_cancelamento"] = "O cancelamento exige uma justificativa."
        if errors:
            raise ValidationError(errors)

    @property
    def total_recebido(self) -> Decimal:
        if not self.pk:
            return Decimal("0.00")
        return _dinheiro(
            self.recebimentos.filter(situacao=RecebimentoLeite.Situacao.CONFIRMADO).aggregate(
                total=Sum("valor")
            )["total"]
        )

    @property
    def saldo(self) -> Decimal:
        return _dinheiro(self.valor_liquido_calculado - self.total_recebido)

    @property
    def diferencas(self) -> dict[str, Decimal]:
        pares = {
            "litros": (self.total_litros_informado, self.total_litros_calculado),
            "valor_bruto": (self.valor_bruto_informado, self.valor_bruto_calculado),
            "bonificacoes": (self.bonificacoes_informadas, self.bonificacoes_calculadas),
            "descontos": (self.descontos_informados, self.descontos_calculados),
            "valor_liquido": (self.valor_liquido_informado, self.valor_liquido_calculado),
        }
        resultado: dict[str, Decimal] = {}
        for chave, (informado, calculado) in pares.items():
            if informado is None:
                resultado[chave] = Decimal("0.000") if chave == "litros" else Decimal("0.00")
            elif chave == "litros":
                resultado[chave] = (informado - calculado).quantize(Decimal("0.001"))
            else:
                resultado[chave] = _dinheiro(informado - calculado)
        return resultado


class RecebimentoLeite(TimeStampedUUIDModel, SoftDeleteModel):
    class FormaPagamento(models.TextChoices):
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        PIX = "PIX", "PIX"
        DINHEIRO = "DINHEIRO", "Dinheiro"
        CHEQUE = "CHEQUE", "Cheque"
        DEPOSITO = "DEPOSITO", "Depósito"
        OUTRO = "OUTRO", "Outro"

    class Situacao(models.TextChoices):
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        CANCELADO = "CANCELADO", "Cancelado"

    fechamento = models.ForeignKey(
        FechamentoLeite,
        verbose_name="fechamento",
        related_name="recebimentos",
        on_delete=models.PROTECT,
    )
    data = models.DateField("data", default=timezone.localdate)
    valor = models.DecimalField(
        "valor", max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    forma_pagamento = models.CharField(
        "forma de pagamento", max_length=20, choices=FormaPagamento.choices
    )
    referencia = models.CharField("referência", max_length=150, blank=True)
    anexo = models.FileField(
        "anexo", upload_to=caminho_anexo_recebimento, validators=[validar_anexo], blank=True
    )
    observacoes = models.TextField("observações", blank=True)
    situacao = models.CharField(
        "situação", max_length=12, choices=Situacao.choices, default=Situacao.CONFIRMADO
    )
    justificativa_excesso = models.TextField("justificativa para pagamento excedente", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        ordering = ("-data", "-criado_em")
        verbose_name = "recebimento de leite"
        verbose_name_plural = "recebimentos de leite"
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0), name="financeiro_recebimento_valor_positivo"
            )
        ]
        indexes = [
            models.Index(fields=("fechamento", "situacao"), name="fin_receb_fech_sit_idx"),
            models.Index(fields=("data",), name="fin_receb_data_idx"),
        ]

    def __str__(self) -> str:
        return f"R$ {self.valor} em {self.data:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data and self.data > timezone.localdate():
            errors["data"] = "A data do recebimento não pode estar no futuro."
        if self.fechamento_id and self.fechamento.situacao == FechamentoLeite.Situacao.CANCELADO:
            errors["fechamento"] = "Não é possível receber um fechamento cancelado."
        if self.situacao == self.Situacao.CANCELADO and not self.motivo_cancelamento.strip():
            errors["motivo_cancelamento"] = "O cancelamento exige uma justificativa."
        if errors:
            raise ValidationError(errors)
