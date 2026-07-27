from django.contrib import admin

from .models import ArquivoAnexo


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
