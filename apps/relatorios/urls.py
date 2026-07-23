from django.urls import path

from . import views

app_name = "relatorios"
urlpatterns = [
    path("", views.index, name="index"),
    path("rebanho/", views.rebanho, name="rebanho"),
    path("reproducao/", views.reproducao, name="reproducao"),
    path("leite/", views.leite, name="leite"),
    path("financeiro/", views.financeiro, name="financeiro"),
    path("fechamentos/", views.fechamentos, name="fechamentos"),
    path("recebimentos/", views.recebimentos, name="recebimentos"),
]
