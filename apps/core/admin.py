from django.contrib import admin

from .models import Alerta, ArquivoAnexo, ConfiguracaoSistema


@admin.register(ConfiguracaoSistema)
class ConfiguracaoSistemaAdmin(admin.ModelAdmin):
    readonly_fields = ("atualizado_em",)

    def has_add_permission(self, request):
        return not ConfiguracaoSistema.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "nivel", "data_referencia", "resolvido")
    list_filter = ("nivel", "tipo", "resolvido")
    search_fields = ("titulo", "mensagem", "identificador")
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(ArquivoAnexo)
class ArquivoAnexoAdmin(admin.ModelAdmin):
    list_display = (
        "nome_original",
        "mime_type",
        "tamanho_bytes",
        "campo",
        "enviado_por",
        "enviado_em",
        "ativo",
    )
    list_filter = ("ativo", "mime_type", "campo", "enviado_em")
    search_fields = ("nome_original", "caminho", "object_id")
    readonly_fields = (
        "content_type",
        "object_id",
        "campo",
        "caminho",
        "nome_original",
        "mime_type",
        "tamanho_bytes",
        "enviado_por",
        "enviado_em",
        "ativo",
        "substituido_em",
        "criado_em",
        "atualizado_em",
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
