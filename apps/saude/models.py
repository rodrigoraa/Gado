from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import SoftDeleteModel, TimeStampedUUIDModel


class ProdutoSaude(TimeStampedUUIDModel):
    class Tipo(models.TextChoices):
        VACINA = "VACINA", "Vacina"
        VERMIFUGO = "VERMIFUGO", "Vermífugo"
        MEDICAMENTO = "MEDICAMENTO", "Medicamento"
        TRATAMENTO = "TRATAMENTO", "Tratamento"
        OUTRO = "OUTRO", "Outro"

    nome = models.CharField("nome", max_length=160)
    tipo = models.CharField("tipo", max_length=16, choices=Tipo.choices)
    fabricante = models.CharField("fabricante", max_length=160, blank=True)
    unidade = models.CharField("unidade", max_length=30, default="mL")
    carencia_padrao_dias = models.PositiveIntegerField("carência padrão (dias)", default=0)
    carencia_padrao_horas = models.PositiveIntegerField("carência padrão (horas)", default=0)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ("nome", "fabricante")
        verbose_name = "produto de saúde"
        verbose_name_plural = "produtos de saúde"
        constraints = [
            models.UniqueConstraint(
                fields=("nome", "fabricante"), name="saude_produto_nome_fabricante_unico"
            )
        ]
        indexes = [models.Index(fields=("tipo", "ativo"), name="saude_prod_tipo_ativo_idx")]

    def __str__(self) -> str:
        return f"{self.nome} ({self.fabricante})" if self.fabricante else self.nome


class Tratamento(TimeStampedUUIDModel, SoftDeleteModel):
    class Situacao(models.TextChoices):
        REGISTRADO = "REGISTRADO", "Registrado"
        CORRIGIDO = "CORRIGIDO", "Corrigido"
        CANCELADO = "CANCELADO", "Cancelado"

    animal = models.ForeignKey(
        "rebanho.Animal",
        verbose_name="animal",
        related_name="tratamentos",
        on_delete=models.PROTECT,
    )
    produto = models.ForeignKey(
        ProdutoSaude,
        verbose_name="produto",
        related_name="tratamentos",
        on_delete=models.PROTECT,
    )
    data_hora = models.DateTimeField("data e hora", default=timezone.now)
    dose = models.DecimalField(
        "dose", max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    unidade = models.CharField("unidade", max_length=30)
    responsavel = models.CharField("responsável", max_length=150, blank=True)
    motivo = models.TextField("motivo")
    carencia_dias = models.PositiveIntegerField(
        "carência (dias)",
        default=0,
        help_text="Confirme a carência conforme a bula e a orientação do médico-veterinário.",
    )
    carencia_horas = models.PositiveIntegerField("carência adicional (horas)", default=0)
    data_liberacao = models.DateTimeField("data de liberação", editable=False)
    observacoes = models.TextField("observações", blank=True)
    situacao = models.CharField(
        "situação", max_length=12, choices=Situacao.choices, default=Situacao.REGISTRADO
    )
    motivo_correcao = models.TextField("motivo da correção", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        ordering = ("-data_hora", "animal")
        verbose_name = "tratamento"
        verbose_name_plural = "tratamentos"
        constraints = [
            models.CheckConstraint(condition=Q(dose__gt=0), name="saude_tratamento_dose_positiva"),
        ]
        indexes = [
            models.Index(fields=("animal", "data_liberacao"), name="saude_trat_animal_lib_idx"),
            models.Index(fields=("situacao", "data_hora"), name="saude_trat_sit_data_idx"),
            models.Index(fields=("data_liberacao",), name="saude_trat_liberacao_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.animal} — {self.produto} em {timezone.localtime(self.data_hora):%d/%m/%Y %H:%M}"
        )

    def calcular_liberacao(self) -> None:
        if self.data_hora:
            self.data_liberacao = self.data_hora + timedelta(
                days=self.carencia_dias or 0, hours=self.carencia_horas or 0
            )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data_hora and self.data_hora > timezone.now():
            errors["data_hora"] = "A aplicação não pode estar no futuro."
        if self.situacao == self.Situacao.CORRIGIDO and not self.motivo_correcao.strip():
            errors["motivo_correcao"] = "A correção exige uma justificativa."
        if self.situacao == self.Situacao.CANCELADO and not self.motivo_cancelamento.strip():
            errors["motivo_cancelamento"] = "O cancelamento exige uma justificativa."
        if errors:
            raise ValidationError(errors)
        self.calcular_liberacao()

    def save(self, *args: object, **kwargs: object) -> None:
        self.calcular_liberacao()
        super().save(*args, **kwargs)

    @property
    def em_carencia(self) -> bool:
        return (
            self.ativo_registro
            and self.situacao != self.Situacao.CANCELADO
            and self.data_hora <= timezone.now() < self.data_liberacao
        )


class EventoSaude(TimeStampedUUIDModel, SoftDeleteModel):
    """Ocorrência clínica avulsa preservada como parte do prontuário do animal."""

    class Tipo(models.TextChoices):
        DOENCA = "DOENCA", "Doença"
        PROCEDIMENTO = "PROCEDIMENTO", "Procedimento"
        EXAME = "EXAME", "Exame"
        OBSERVACAO_VETERINARIA = "OBSERVACAO_VETERINARIA", "Observação veterinária"

    class Situacao(models.TextChoices):
        REGISTRADO = "REGISTRADO", "Registrado"
        CORRIGIDO = "CORRIGIDO", "Corrigido"
        CANCELADO = "CANCELADO", "Cancelado"

    animal = models.ForeignKey(
        "rebanho.Animal",
        verbose_name="animal",
        related_name="eventos_saude",
        on_delete=models.PROTECT,
    )
    tipo = models.CharField("tipo", max_length=24, choices=Tipo.choices)
    data_hora = models.DateTimeField("data e hora efetiva", default=timezone.now)
    titulo = models.CharField("título", max_length=180)
    descricao = models.TextField("descrição")
    veterinario = models.CharField("médico-veterinário", max_length=160, blank=True)
    responsavel = models.CharField("outro responsável", max_length=160, blank=True)
    resultado = models.TextField("resultado/conclusão", blank=True)
    situacao = models.CharField(
        "situação", max_length=12, choices=Situacao.choices, default=Situacao.REGISTRADO
    )
    motivo_correcao = models.TextField("justificativa da correção", blank=True)
    motivo_cancelamento = models.TextField("justificativa do cancelamento", blank=True)

    class Meta:
        ordering = ("-data_hora", "animal", "titulo")
        verbose_name = "evento de saúde"
        verbose_name_plural = "eventos de saúde"
        indexes = [
            models.Index(fields=("animal", "data_hora"), name="saude_evento_animal_data_idx"),
            models.Index(fields=("tipo", "data_hora"), name="saude_evento_tipo_data_idx"),
            models.Index(fields=("situacao", "data_hora"), name="saude_evento_sit_data_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()}: {self.titulo} — {self.animal}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.data_hora and self.data_hora > timezone.now():
            errors["data_hora"] = "A data efetiva do evento não pode estar no futuro."
        if not self.veterinario.strip() and not self.responsavel.strip():
            errors["responsavel"] = (
                "Informe o médico-veterinário ou outro responsável pelo registro."
            )
        if self.situacao == self.Situacao.CORRIGIDO and not self.motivo_correcao.strip():
            errors["motivo_correcao"] = "A correção exige uma justificativa."
        if self.situacao == self.Situacao.CANCELADO:
            if not self.motivo_cancelamento.strip():
                errors["motivo_cancelamento"] = "O cancelamento exige uma justificativa."
            if self.ativo_registro:
                errors["ativo_registro"] = "Um evento cancelado não pode permanecer ativo."
            if self.cancelado_em is None:
                errors["cancelado_em"] = "Informe quando o evento foi cancelado."
        elif not self.ativo_registro:
            errors["ativo_registro"] = "Somente eventos cancelados podem ficar inativos."
        if errors:
            raise ValidationError(errors)

    @property
    def cancelado(self) -> bool:
        return self.situacao == self.Situacao.CANCELADO

    def delete(
        self, using: object = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        del using, keep_parents
        raise ValidationError(
            "Eventos de saúde pertencem ao prontuário e devem ser cancelados, nunca excluídos."
        )
