import pytest
from django.contrib.auth import get_user_model

ROTAS_AUTENTICADAS = (
    "/",
    "/configuracoes/",
    "/alertas/",
    "/rebanho/",
    "/rebanho/animais/novo/",
    "/rebanho/racas/",
    "/rebanho/lotes/",
    "/reproducao/",
    "/reproducao/coberturas/nova/",
    "/reproducao/diagnosticos/novo/",
    "/reproducao/perdas/nova/",
    "/reproducao/partos/",
    "/reproducao/partos/novo/",
    "/lactacoes/",
    "/lactacoes/nova/",
    "/leite/",
    "/leite/ordenhas/nova/",
    "/leite/producoes/",
    "/leite/destinos/",
    "/saude/",
    "/saude/produtos/",
    "/saude/tratamentos/novo/",
    "/financeiro/",
    "/financeiro/laticinios/",
    "/financeiro/precos/",
    "/financeiro/entregas/",
    "/financeiro/fechamentos/",
    "/financeiro/recebimentos/",
    "/relatorios/",
    "/relatorios/rebanho/",
    "/relatorios/reproducao/",
    "/relatorios/leite/",
    "/relatorios/financeiro/",
    "/relatorios/fechamentos/",
    "/relatorios/recebimentos/",
    "/auditoria/",
    "/senha/alterar/",
)


@pytest.fixture
def usuario(db):
    return get_user_model().objects.create_user(username="operador", password="senha-forte-123")


@pytest.mark.parametrize("rota", ROTAS_AUTENTICADAS)
def test_rotas_principais_renderizam(client, usuario, rota):
    client.force_login(usuario)
    resposta = client.get(rota)
    assert resposta.status_code == 200, rota
    assert b"<!doctype html>" in resposta.content.lower(), rota


@pytest.mark.django_db
def test_htmx_retorna_apenas_resultados(client, usuario):
    client.force_login(usuario)
    resposta = client.get("/rebanho/?q=ABC", HTTP_HX_REQUEST="true")
    assert resposta.status_code == 200
    assert b"<!doctype html>" not in resposta.content.lower()


@pytest.mark.django_db
def test_post_sem_csrf_e_rejeitado(usuario):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(usuario)
    resposta = client.post("/configuracoes/", {"nome_propriedade": "Sem token"})
    assert resposta.status_code == 403
