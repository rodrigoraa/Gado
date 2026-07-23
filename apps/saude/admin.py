from django.contrib import admin

from .models import EventoSaude, ProdutoSaude, Tratamento


class SemExclusaoAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(ProdutoSaude)
class ProdutoSaudeAdmin(SemExclusaoAdmin):
    list_display = ("nome", "tipo", "fabricante", "unidade", "carencia_padrao_dias", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("nome", "fabricante", "observacoes")
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(Tratamento)
class TratamentoAdmin(SemExclusaoAdmin):
    list_display = (
        "data_hora",
        "animal",
        "produto",
        "dose",
        "data_liberacao",
        "situacao",
        "em_carencia",
    )
    list_filter = ("situacao", "produto__tipo", "ativo_registro", "data_hora", "data_liberacao")
    search_fields = (
        "animal__identificacao",
        "animal__nome",
        "produto__nome",
        "responsavel",
        "motivo",
    )
    autocomplete_fields = ("animal", "produto")
    readonly_fields = ("id", "data_liberacao", "criado_em", "atualizado_em", "cancelado_em")


@admin.register(EventoSaude)
class EventoSaudeAdmin(admin.ModelAdmin):
    """Consulta técnica; mutações devem passar pelos services auditáveis da aplicação."""

    list_display = ("data_hora", "animal", "tipo", "titulo", "situacao")
    list_filter = ("tipo", "situacao", "ativo_registro", "data_hora")
    search_fields = (
        "animal__identificacao",
        "animal__identificacao_provisoria",
        "animal__nome",
        "titulo",
        "descricao",
        "veterinario",
        "responsavel",
        "resultado",
    )
    date_hierarchy = "data_hora"
    readonly_fields = [field.name for field in EventoSaude._meta.fields]

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
