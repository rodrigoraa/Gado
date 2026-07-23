from django.contrib import admin

from apps.rebanho.admin import SomenteLeituraAdminMixin, SomenteLeituraInlineMixin

from .models import EntregaLeite, FechamentoLeite, Laticinio, PrecoLeite, RecebimentoLeite


class SemExclusaoAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(Laticinio)
class LaticinioAdmin(SemExclusaoAdmin):
    list_display = ("razao_social", "nome_fantasia", "codigo_produtor", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("razao_social", "nome_fantasia", "cpf_cnpj", "codigo_produtor")
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(PrecoLeite)
class PrecoLeiteAdmin(SemExclusaoAdmin):
    list_display = ("laticinio", "data_inicial", "data_final", "valor_litro", "atualizado_em")
    list_filter = ("laticinio", "data_inicial")
    search_fields = ("laticinio__razao_social", "laticinio__nome_fantasia", "observacoes")
    readonly_fields = ("id", "criado_em", "atualizado_em")

    def get_readonly_fields(self, request, obj=None):  # type: ignore[no-untyped-def]
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            # Correções de vigência/valor passam pela interface que exige motivo.
            campos.extend(("laticinio", "data_inicial", "data_final", "valor_litro"))
        return tuple(dict.fromkeys(campos))


@admin.register(EntregaLeite)
class EntregaLeiteAdmin(SemExclusaoAdmin):
    list_display = (
        "data_coleta",
        "quantidade_litros",
        "valor_litro",
        "valor_bruto",
        "valor_liquido",
        "situacao",
    )
    list_filter = ("situacao", "preco_manual", "ativo_registro", "data_coleta")
    search_fields = ("numero_documento", "observacoes", "laticinio__razao_social")
    date_hierarchy = "data_coleta"
    readonly_fields = (
        "id",
        "valor_bruto",
        "total_bonificacoes",
        "total_descontos",
        "valor_liquido",
        "criado_em",
        "atualizado_em",
        "cancelado_em",
    )


class RecebimentoInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = RecebimentoLeite
    extra = 0
    readonly_fields = ("criado_em", "atualizado_em", "cancelado_em")
    can_delete = False


@admin.register(FechamentoLeite)
class FechamentoLeiteAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = (
        "competencia",
        "laticinio",
        "total_litros_calculado",
        "valor_liquido_calculado",
        "situacao",
        "data_prevista_pagamento",
    )
    list_filter = ("situacao", "laticinio", "competencia", "ativo_registro")
    search_fields = ("numero_demonstrativo", "laticinio__razao_social", "observacoes")
    filter_horizontal = ("entregas",)
    readonly_fields = (
        "id",
        "total_litros_calculado",
        "valor_bruto_calculado",
        "bonificacoes_calculadas",
        "descontos_calculados",
        "valor_liquido_calculado",
        "criado_em",
        "atualizado_em",
        "cancelado_em",
    )
    inlines = (RecebimentoInline,)


@admin.register(RecebimentoLeite)
class RecebimentoLeiteAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = ("data", "fechamento", "valor", "forma_pagamento", "situacao")
    list_filter = ("situacao", "forma_pagamento", "data", "ativo_registro")
    search_fields = ("referencia", "observacoes", "fechamento__numero_demonstrativo")
    readonly_fields = ("id", "criado_em", "atualizado_em", "cancelado_em")
