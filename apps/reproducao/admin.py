from django.contrib import admin

from apps.rebanho.admin import (
    SemExclusaoAdminMixin,
    SomenteLeituraAdminMixin,
    SomenteLeituraInlineMixin,
)

from .models import (
    Cobertura,
    DiagnosticoGestacao,
    HistoricoCobertura,
    HistoricoParto,
    Nascimento,
    Parto,
    PerdaGestacional,
)


class DiagnosticoInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = DiagnosticoGestacao
    fields = ("data", "resultado", "metodo", "responsavel", "nova_previsao_parto")
    readonly_fields = fields
    show_change_link = True


class PerdaInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = PerdaGestacional
    fields = ("data", "tipo", "responsavel")
    readonly_fields = fields
    show_change_link = True


class HistoricoCoberturaInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = HistoricoCobertura
    fields = (
        "evento",
        "situacao_anterior",
        "situacao_nova",
        "previsao_anterior",
        "previsao_nova",
        "justificativa",
        "criado_em",
    )
    readonly_fields = fields


@admin.register(Cobertura)
class CoberturaAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = (
        "vaca",
        "data",
        "tipo",
        "situacao",
        "previsao_atual_parto",
        "touro",
    )
    list_filter = ("situacao", "tipo", "forma_identificacao", "data")
    search_fields = (
        "vaca__identificacao",
        "vaca__identificacao_provisoria",
        "vaca__nome",
        "touro__identificacao",
    )
    autocomplete_fields = ("vaca", "touro")
    readonly_fields = (
        "id",
        "data_original",
        "previsao_original_parto",
        "criado_em",
        "atualizado_em",
    )
    date_hierarchy = "data"
    inlines = (DiagnosticoInline, PerdaInline, HistoricoCoberturaInline)


@admin.register(DiagnosticoGestacao)
class DiagnosticoGestacaoAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = ("vaca", "data", "resultado", "metodo", "cobertura")
    list_filter = ("resultado", "metodo", "data")
    search_fields = ("vaca__identificacao", "vaca__nome", "responsavel")
    autocomplete_fields = ("vaca", "cobertura")
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(PerdaGestacional)
class PerdaGestacionalAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("vaca", "data", "tipo", "cobertura", "responsavel")
    list_filter = ("tipo", "data")
    search_fields = ("vaca__identificacao", "vaca__nome", "responsavel")
    autocomplete_fields = ("vaca", "cobertura")
    readonly_fields = ("id", "criado_em", "atualizado_em")


class NascimentoInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = Nascimento
    fields = ("animal", "situacao", "peso_ao_nascer_kg", "observacoes")
    readonly_fields = fields
    show_change_link = True


class HistoricoPartoInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = HistoricoParto
    fields = ("evento", "justificativa", "criado_em")
    readonly_fields = fields


@admin.register(Parto)
class PartoAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = (
        "vaca",
        "data_hora",
        "resultado",
        "quantidade_bezerros",
        "situacao",
    )
    list_filter = ("situacao", "resultado", "necessitou_auxilio", "data_hora")
    search_fields = ("vaca__identificacao", "vaca__nome", "responsavel")
    autocomplete_fields = ("vaca", "cobertura")
    readonly_fields = ("id", "criado_em", "atualizado_em")
    date_hierarchy = "data_hora"
    inlines = (NascimentoInline, HistoricoPartoInline)


@admin.register(Nascimento)
class NascimentoAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("animal", "parto", "situacao", "peso_ao_nascer_kg")
    list_filter = ("situacao",)
    search_fields = ("animal__identificacao", "animal__nome")
    autocomplete_fields = ("animal", "parto")
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(HistoricoCobertura, HistoricoParto)
class HistoricoReprodutivoAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    readonly_fields = ("id", "criado_em", "atualizado_em")

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
