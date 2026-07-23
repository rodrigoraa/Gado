from django.conf import settings
from django.db import models


class UltimaAtividade(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ultima_atividade"
    )
    data_hora = models.DateTimeField(auto_now=True)
    caminho = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "última atividade"
        verbose_name_plural = "últimas atividades"

    def __str__(self) -> str:
        return f"{self.usuario}: {self.data_hora:%d/%m/%Y %H:%M}"
