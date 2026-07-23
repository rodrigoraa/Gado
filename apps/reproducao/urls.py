from django.urls import path

from . import views

app_name = "reproducao"

urlpatterns = [
    path("", views.CoberturaListView.as_view(), name="coberturas"),
    path(
        "por-boi/",
        views.CoberturaPorTouroListView.as_view(),
        name="coberturas_por_touro",
    ),
    path("coberturas/nova/", views.CoberturaCreateView.as_view(), name="cobertura_nova"),
    path(
        "coberturas/<uuid:cobertura_id>/",
        views.CoberturaDetailView.as_view(),
        name="cobertura_detalhe",
    ),
    path(
        "coberturas/<uuid:cobertura_id>/alterar-data/",
        views.CoberturaAlterarDataView.as_view(),
        name="cobertura_alterar_data",
    ),
    path(
        "coberturas/<uuid:cobertura_id>/cancelar/",
        views.CoberturaCancelarView.as_view(),
        name="cobertura_cancelar",
    ),
    path("diagnosticos/novo/", views.DiagnosticoCreateView.as_view(), name="diagnostico_novo"),
    path(
        "coberturas/<uuid:cobertura_id>/diagnostico/",
        views.DiagnosticoCreateView.as_view(),
        name="cobertura_diagnostico",
    ),
    path("perdas/nova/", views.PerdaCreateView.as_view(), name="perda_nova"),
    path(
        "coberturas/<uuid:cobertura_id>/perda/",
        views.PerdaCreateView.as_view(),
        name="cobertura_perda",
    ),
    path("partos/", views.PartoListView.as_view(), name="partos"),
    path("partos/novo/", views.PartoCreateView.as_view(), name="parto_novo"),
    path(
        "coberturas/<uuid:cobertura_id>/parto/",
        views.PartoCreateView.as_view(),
        name="cobertura_parto",
    ),
    path("partos/<uuid:parto_id>/", views.PartoDetailView.as_view(), name="parto_detalhe"),
    path(
        "partos/<uuid:parto_id>/corrigir/",
        views.PartoCorrigirView.as_view(),
        name="parto_corrigir",
    ),
    path(
        "partos/<uuid:parto_id>/cancelar/",
        views.PartoCancelarView.as_view(),
        name="parto_cancelar",
    ),
]
