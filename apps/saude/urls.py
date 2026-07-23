from django.urls import path

from . import views

app_name = "saude"

urlpatterns = [
    path("", views.TratamentoListView.as_view(), name="inicio"),
    path("eventos/", views.EventoSaudeListView.as_view(), name="eventos"),
    path("eventos/novo/", views.EventoSaudeFormView.as_view(), name="evento_novo"),
    path(
        "eventos/<uuid:pk>/",
        views.EventoSaudeDetailView.as_view(),
        name="evento_detalhe",
    ),
    path(
        "eventos/<uuid:pk>/editar/",
        views.EventoSaudeFormView.as_view(),
        name="evento_editar",
    ),
    path(
        "eventos/<uuid:pk>/cancelar/",
        views.EventoSaudeCancelarView.as_view(),
        name="evento_cancelar",
    ),
    path("produtos/", views.ProdutoListView.as_view(), name="produtos"),
    path("produtos/novo/", views.ProdutoFormView.as_view(), name="produto_novo"),
    path("produtos/<uuid:pk>/editar/", views.ProdutoFormView.as_view(), name="produto_editar"),
    path("tratamentos/", views.TratamentoListView.as_view(), name="tratamentos"),
    path("tratamentos/novo/", views.TratamentoFormView.as_view(), name="tratamento_novo"),
    path("tratamentos/<uuid:pk>/", views.TratamentoDetailView.as_view(), name="tratamento_detalhe"),
    path(
        "tratamentos/<uuid:pk>/editar/",
        views.TratamentoFormView.as_view(),
        name="tratamento_editar",
    ),
    path(
        "tratamentos/<uuid:pk>/cancelar/",
        views.TratamentoCancelarView.as_view(),
        name="tratamento_cancelar",
    ),
    path(
        "tratamentos/<uuid:pk>/descarte/",
        views.DescarteLeiteView.as_view(),
        name="tratamento_descarte",
    ),
]
