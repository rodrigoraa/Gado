import contextlib
import importlib
import io

import pytest
from django.contrib.auth import get_user_model

ROTAS_RELATORIO = (
    "/relatorios/rebanho/",
    "/relatorios/reproducao/",
    "/relatorios/leite/",
)


def _weasyprint_disponivel() -> bool:
    """Detecta as bibliotecas nativas sem poluir a coleta no Windows."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            importlib.import_module("weasyprint")
    except (ImportError, OSError):
        return False
    return True


WEASYPRINT_DISPONIVEL = _weasyprint_disponivel()


@pytest.fixture
def cliente_autenticado(client, db):
    usuario = get_user_model().objects.create_user(
        username="relatorios", password="senha-forte-123"
    )
    client.force_login(usuario)
    return client


@pytest.mark.parametrize("rota", ROTAS_RELATORIO)
def test_relatorios_exportam_xlsx(cliente_autenticado, rota):
    resposta = cliente_autenticado.get(rota, {"formato": "xlsx"})
    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resposta.content.startswith(b"PK")


@pytest.mark.parametrize("rota", ROTAS_RELATORIO)
@pytest.mark.skipif(
    not WEASYPRINT_DISPONIVEL,
    reason="WeasyPrint requer as bibliotecas nativas fornecidas pela imagem Docker",
)
def test_relatorios_exportam_pdf(cliente_autenticado, rota):
    resposta = cliente_autenticado.get(rota, {"formato": "pdf"})
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF")
