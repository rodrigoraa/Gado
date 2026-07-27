from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedUUIDModel(models.Model):
    """Base para as entidades de negócio que precisam de identidade estável."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Marca registros como inativos sem apagar seu histórico."""

    ativo_registro = models.BooleanField(default=True, db_index=True)
    cancelado_em = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

    def cancelar(self) -> None:
        self.ativo_registro = False
        self.cancelado_em = timezone.now()


class ConfiguracaoSistema(models.Model):
    """Parâmetros internos usados pelos cálculos do sistema."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    nome_propriedade = models.CharField(max_length=120, default="Minha propriedade")
    gestacao_dias = models.PositiveSmallIntegerField(default=283)
    margem_parto_dias = models.PositiveSmallIntegerField(default=7)
    dias_diagnostico = models.PositiveSmallIntegerField(default=45)
    idade_bezerro_meses = models.PositiveSmallIntegerField(default=12)
    tolerancia_divergencia_litros = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0.500"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tolerancia_divergencia_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do sistema"
        verbose_name_plural = "configuração do sistema"

    def __str__(self) -> str:
        return self.nome_propriedade

    def save(self, *args: object, **kwargs: object) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls) -> ConfiguracaoSistema:
        objeto, _ = cls.objects.get_or_create(pk=1)
        return objeto


class ArquivoAnexo(TimeStampedUUIDModel):
    """Metadados auditáveis de cada upload privado, sem expor a mídia publicamente."""

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64, db_index=True)
    objeto = GenericForeignKey("content_type", "object_id")
    campo = models.CharField(max_length=80)
    caminho = models.CharField(max_length=500)
    nome_original = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120)
    tamanho_bytes = models.PositiveBigIntegerField()
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="arquivos_enviados",
    )
    enviado_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True, db_index=True)
    substituido_em = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "metadado de arquivo privado"
        verbose_name_plural = "metadados de arquivos privados"
        ordering = ("-enviado_em",)
        indexes = [
            models.Index(
                fields=("content_type", "object_id", "campo", "ativo"),
                name="core_arquivo_obj_campo_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("content_type", "object_id", "campo"),
                condition=models.Q(ativo=True),
                name="core_arquivo_ativo_obj_campo_unico",
            )
        ]

    def __str__(self) -> str:
        return f"{self.nome_original} ({self.mime_type})"
