from django.contrib import admin

from apps.rebanho.admin import SomenteLeituraAdminMixin, SomenteLeituraInlineMixin

from .models import DestinoLeite, Ordenha, ProducaoAnimal


class SemExclusaoAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


class ProducaoAnimalInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = ProducaoAnimal
    extra = 0
    autocomplete_fields = ("vaca", "lactacao")
    readonly_fields = ("criado_em", "atualizado_em")
    can_delete = False


class DestinoLeiteInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = DestinoLeite
    fk_name = "ordenha"
    extra = 0
    readonly_fields = ("criado_em", "atualizado_em")
    can_delete = False


@admin.register(Ordenha)
class OrdenhaAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = (
        "data",
        "periodo",
        "quantidade_total",
        "quantidade_vacas",
        "situacao",
        "ativo_registro",
    )
    list_filter = ("periodo", "modo", "situacao", "ativo_registro", "data")
    search_fields = ("responsavel", "observacoes", "motivo_correcao")
    date_hierarchy = "data"
    readonly_fields = ("id", "criado_em", "atualizado_em", "cancelado_em")
    inlines = (ProducaoAnimalInline, DestinoLeiteInline)


@admin.register(ProducaoAnimal)
class ProducaoAnimalAdmin(SomenteLeituraAdminMixin, admin.ModelAdmin):
    list_display = ("ordenha", "vaca", "lactacao", "quantidade_litros")
    list_filter = ("ordenha__data",)
    search_fields = ("vaca__identificacao", "vaca__nome", "observacoes")
    autocomplete_fields = ("ordenha", "vaca", "lactacao")
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(DestinoLeite)
class DestinoLeiteAdmin(SemExclusaoAdmin):
    list_display = ("data", "tipo", "quantidade_litros", "ordenha", "tratamento")
    list_filter = ("tipo", "data")
    search_fields = ("observacoes",)
    autocomplete_fields = ("ordenha", "tratamento")
    readonly_fields = ("id", "criado_em", "atualizado_em")
