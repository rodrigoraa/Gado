from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedUUIDModel


class RegistroAuditoria(TimeStampedUUIDModel):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    data_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    ip = models.GenericIPAddressField(blank=True, null=True)
    cf_connecting_ip = models.GenericIPAddressField(blank=True, null=True)
    x_forwarded_for = models.CharField(max_length=255, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    modulo = models.CharField(max_length=80, db_index=True)
    entidade = models.CharField(max_length=120, db_index=True)
    identificador = models.CharField(max_length=80, db_index=True)
    operacao = models.CharField(max_length=40, db_index=True)
    dados_anteriores = models.JSONField(default=dict, blank=True)
    dados_novos = models.JSONField(default=dict, blank=True)
    justificativa = models.TextField(blank=True)

    class Meta:
        ordering = ["-data_hora"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        indexes = [models.Index(fields=["modulo", "entidade", "identificador"])]

    def __str__(self) -> str:
        return f"{self.data_hora:%d/%m/%Y %H:%M} — {self.entidade} — {self.operacao}"
