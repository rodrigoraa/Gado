from django.contrib import admin

from .models import Animal, HistoricoParentesco, Lote, MovimentacaoLote, Pesagem, Raca


class SemExclusaoAdminMixin:
    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


class SomenteLeituraAdminMixin(SemExclusaoAdminMixin):
    """Mantém o cadastro consultável, mas obriga mutações a passarem pelos services."""

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


class SomenteLeituraInlineMixin:
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


class PesagemInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = Pesagem
    fields = ("data", "peso_kg", "responsavel")
    readonly_fields = fields
    show_change_link = True


class MovimentacaoLoteInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = MovimentacaoLote
    fk_name = "animal"
    fields = ("data", "lote_anterior", "novo_lote", "motivo")
    readonly_fields = fields
    show_change_link = True


class HistoricoParentescoInline(SomenteLeituraInlineMixin, admin.TabularInline):
    model = HistoricoParentesco
    fk_name = "animal"
    fields = (
        "mae_anterior",
        "mae_nova",
        "pai_anterior",
        "pai_novo",
        "justificativa",
        "criado_em",
    )
    readonly_fields = fields


@admin.register(Animal)
class AnimalAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = (
        "identificador_exibicao",
        "cor",
        "sexo",
        "tipo_animal",
        "situacao",
        "lote",
        "peso_atual",
    )
    list_filter = ("situacao", "sexo", "tipo_animal", "origem", "raca", "lote")
    search_fields = ("identificacao", "identificacao_provisoria", "nome")
    autocomplete_fields = ("mae", "pai", "raca", "lote")
    readonly_fields = ("id", "idade", "criado_em", "atualizado_em")
    date_hierarchy = "data_nascimento"
    inlines = (PesagemInline, MovimentacaoLoteInline, HistoricoParentescoInline)
    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "id",
                    "identificacao",
                    "identificacao_provisoria",
                    "nome",
                    "cor",
                    "foto",
                )
            },
        ),
        (
            "Dados zootécnicos",
            {
                "fields": (
                    "sexo",
                    "tipo_animal",
                    "data_nascimento",
                    "data_nascimento_aproximada",
                    "idade",
                    "raca",
                    "mae",
                    "pai",
                    "peso_atual",
                )
            },
        ),
        (
            "Situação",
            {
                "fields": (
                    "origem",
                    "data_entrada",
                    "situacao",
                    "data_saida",
                    "motivo_saida",
                    "lote",
                )
            },
        ),
        ("Observações", {"fields": ("observacoes",)}),
        ("Controle", {"fields": ("criado_em", "atualizado_em")}),
    )

    def get_readonly_fields(self, request, obj=None):  # type: ignore[no-untyped-def]
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            # A interface própria exige justificativa e cria HistoricoParentesco.
            campos.extend(("mae", "pai"))
        return tuple(dict.fromkeys(campos))


@admin.register(Raca)
class RacaAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "ativa", "atualizado_em")
    list_filter = ("ativa",)
    search_fields = ("nome",)
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(Lote)
class LoteAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(Pesagem)
class PesagemAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("animal", "data", "peso_kg", "responsavel")
    list_filter = ("data",)
    search_fields = (
        "animal__identificacao",
        "animal__identificacao_provisoria",
        "animal__nome",
        "responsavel",
    )
    autocomplete_fields = ("animal",)
    readonly_fields = ("id", "criado_em", "atualizado_em")
    date_hierarchy = "data"


@admin.register(MovimentacaoLote)
class MovimentacaoLoteAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("animal", "lote_anterior", "novo_lote", "data", "motivo")
    list_filter = ("data", "lote_anterior", "novo_lote")
    search_fields = (
        "animal__identificacao",
        "animal__identificacao_provisoria",
        "motivo",
    )
    autocomplete_fields = ("animal", "lote_anterior", "novo_lote")
    readonly_fields = ("id", "criado_em", "atualizado_em")


@admin.register(HistoricoParentesco)
class HistoricoParentescoAdmin(SemExclusaoAdminMixin, admin.ModelAdmin):
    list_display = ("animal", "mae_anterior", "mae_nova", "pai_anterior", "pai_novo", "criado_em")
    search_fields = ("animal__identificacao", "justificativa")
    readonly_fields = (
        "id",
        "animal",
        "mae_anterior",
        "mae_nova",
        "pai_anterior",
        "pai_novo",
        "justificativa",
        "criado_em",
        "atualizado_em",
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
