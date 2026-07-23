from django.urls import path

from . import views

app_name = "rebanho"

urlpatterns = [
    path("", views.AnimalListView.as_view(), name="animais"),
    path("animais/novo/", views.AnimalFormView.as_view(), name="animal_novo"),
    path(
        "bezerros/novo/",
        views.AnimalFormView.as_view(),
        {"bezerro": True},
        name="bezerro_novo",
    ),
    path(
        "animais/<uuid:animal_id>/",
        views.AnimalDetailView.as_view(),
        name="animal_detalhe",
    ),
    path(
        "animais/<uuid:animal_id>/editar/",
        views.AnimalFormView.as_view(),
        name="animal_editar",
    ),
    path(
        "animais/<uuid:animal_id>/inativar/",
        views.AnimalInativarView.as_view(),
        name="animal_inativar",
    ),
    path(
        "animais/<uuid:animal_id>/excluir/",
        views.AnimalExcluirView.as_view(),
        name="animal_excluir",
    ),
    path("movimentacoes/nova/", views.MovimentacaoCreateView.as_view(), name="movimentacao_nova"),
    path("pesagens/nova/", views.PesagemCreateView.as_view(), name="pesagem_nova"),
    path("racas/", views.RacaListView.as_view(), name="racas"),
    path("racas/nova/", views.RacaFormView.as_view(), name="raca_nova"),
    path(
        "racas/<uuid:object_id>/editar/",
        views.RacaFormView.as_view(),
        name="raca_editar",
    ),
    path("lotes/", views.LoteListView.as_view(), name="lotes"),
    path("lotes/novo/", views.LoteFormView.as_view(), name="lote_novo"),
    path(
        "lotes/<uuid:object_id>/editar/",
        views.LoteFormView.as_view(),
        name="lote_editar",
    ),
]
