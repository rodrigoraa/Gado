from django.contrib import admin

from apps.rebanho.admin import SomenteLeituraAdminMixin

from .models import Lactacao


@admin.register(Lactacao)
class LactacaoAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = (
        "vaca",
        "ordem",
        "data_inicio",
        "situacao",
        "data_secagem",
        "data_encerramento",
        "dias_em_lactacao",
    )
    list_filter = ("situacao", "data_inicio", "data_secagem")
    search_fields = (
        "vaca__identificacao",
        "vaca__identificacao_provisoria",
        "vaca__nome",
    )
    autocomplete_fields = ("vaca", "parto")
    readonly_fields = ("id", "ordem", "dias_em_lactacao", "criado_em", "atualizado_em")
    date_hierarchy = "data_inicio"
