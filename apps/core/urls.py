from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("alertas/", views.alertas, name="alertas"),
    path("alertas/<uuid:pk>/resolver/", views.resolver_alerta, name="resolver_alerta"),
    path("arquivos/<path:caminho>", views.arquivo_privado, name="arquivo_privado"),
]
