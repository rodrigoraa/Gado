from django.urls import path

from . import views

app_name = "leite"

urlpatterns = [
    path("", views.OrdenhaListView.as_view(), name="inicio"),
    path("ordenhas/", views.OrdenhaListView.as_view(), name="ordenhas"),
    path("ordenhas/nova/", views.OrdenhaFormView.as_view(), name="ordenha_nova"),
    path("ordenhas/<uuid:pk>/", views.OrdenhaDetailView.as_view(), name="ordenha_detalhe"),
    path(
        "ordenhas/<uuid:pk>/conciliar/",
        views.OrdenhaConciliarView.as_view(),
        name="ordenha_conciliar",
    ),
    path("ordenhas/<uuid:pk>/editar/", views.OrdenhaFormView.as_view(), name="ordenha_editar"),
    path(
        "ordenhas/<uuid:pk>/cancelar/", views.OrdenhaCancelarView.as_view(), name="ordenha_cancelar"
    ),
    path("producoes/", views.ProducaoListView.as_view(), name="producoes"),
    path("producoes/nova/", views.ProducaoFormView.as_view(), name="producao_nova"),
    path("producoes/<uuid:pk>/editar/", views.ProducaoFormView.as_view(), name="producao_editar"),
    path("destinos/", views.DestinoListView.as_view(), name="destinos"),
    path("destinos/novo/", views.DestinoFormView.as_view(), name="destino_novo"),
    path("destinos/<uuid:pk>/editar/", views.DestinoFormView.as_view(), name="destino_editar"),
]
