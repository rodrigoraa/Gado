from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.ConferenciaMensalView.as_view(), name="inicio"),
    path("conferencia/", views.ConferenciaMensalView.as_view(), name="conferencia"),
    path("laticinios/", views.LaticinioListView.as_view(), name="laticinios"),
    path("laticinios/novo/", views.LaticinioFormView.as_view(), name="laticinio_novo"),
    path(
        "laticinios/<uuid:pk>/editar/", views.LaticinioFormView.as_view(), name="laticinio_editar"
    ),
    path("precos/", views.PrecoListView.as_view(), name="precos"),
    path("precos/novo/", views.PrecoFormView.as_view(), name="preco_novo"),
    path("precos/<uuid:pk>/editar/", views.PrecoFormView.as_view(), name="preco_editar"),
    path("entregas/", views.EntregaListView.as_view(), name="entregas"),
    path("entregas/nova/", views.EntregaFormView.as_view(), name="entrega_nova"),
    path("entregas/<uuid:pk>/", views.EntregaDetailView.as_view(), name="entrega_detalhe"),
    path("entregas/<uuid:pk>/editar/", views.EntregaFormView.as_view(), name="entrega_editar"),
    path(
        "entregas/<uuid:pk>/cancelar/", views.EntregaCancelarView.as_view(), name="entrega_cancelar"
    ),
    path("fechamentos/", views.FechamentoListView.as_view(), name="fechamentos"),
    path("fechamentos/novo/", views.FechamentoCreateView.as_view(), name="fechamento_novo"),
    path("fechamentos/<uuid:pk>/", views.FechamentoDetailView.as_view(), name="fechamento_detalhe"),
    path(
        "fechamentos/<uuid:pk>/editar/",
        views.FechamentoUpdateView.as_view(),
        name="fechamento_editar",
    ),
    path(
        "fechamentos/<uuid:pk>/finalizar/",
        views.FechamentoFinalizarView.as_view(),
        name="fechamento_finalizar",
    ),
    path(
        "fechamentos/<uuid:pk>/cancelar/",
        views.FechamentoCancelarView.as_view(),
        name="fechamento_cancelar",
    ),
    path("recebimentos/", views.RecebimentoListView.as_view(), name="recebimentos"),
    path("recebimentos/novo/", views.RecebimentoFormView.as_view(), name="recebimento_novo"),
    path(
        "recebimentos/<uuid:pk>/cancelar/",
        views.RecebimentoCancelarView.as_view(),
        name="recebimento_cancelar",
    ),
    path(
        "arquivos/<str:tipo>/<uuid:pk>/",
        views.ArquivoFinanceiroView.as_view(),
        name="arquivo_privado",
    ),
]
