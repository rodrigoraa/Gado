from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("data_hora", "usuario", "modulo", "entidade", "operacao", "identificador")
    list_filter = ("modulo", "entidade", "operacao")
    search_fields = ("identificador", "justificativa", "usuario__username")
    readonly_fields = [field.name for field in RegistroAuditoria._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
