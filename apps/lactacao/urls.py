from django.urls import path

from . import views

app_name = "lactacao"

urlpatterns = [
    path("", views.LactacaoListView.as_view(), name="lista"),
    path("nova/", views.LactacaoCreateView.as_view(), name="nova"),
    path(
        "partos/<uuid:parto_id>/nova/",
        views.LactacaoCreateView.as_view(),
        name="nova_do_parto",
    ),
    path(
        "<uuid:lactacao_id>/",
        views.LactacaoDetailView.as_view(),
        name="detalhe",
    ),
    path(
        "<uuid:lactacao_id>/secar/",
        views.LactacaoSecarView.as_view(),
        name="secar",
    ),
    path(
        "<uuid:lactacao_id>/encerrar/",
        views.LactacaoEncerrarView.as_view(),
        name="encerrar",
    ),
    path(
        "<uuid:lactacao_id>/cancelar/",
        views.LactacaoCancelarView.as_view(),
        name="cancelar",
    ),
]
