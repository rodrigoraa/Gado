from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("arquivos/<path:caminho>", views.arquivo_privado, name="arquivo_privado"),
]
