import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.core.models import ConfiguracaoSistema
from apps.core.validators import validar_upload_imagem, validar_upload_privado


@pytest.mark.django_db
def test_configuracao_sistema_e_singleton():
    primeira = ConfiguracaoSistema.obter()
    segunda = ConfiguracaoSistema.obter()
    assert primeira.pk == segunda.pk == 1
    assert ConfiguracaoSistema.objects.count() == 1
    assert primeira.gestacao_dias == 283


@pytest.mark.django_db
def test_alteracao_de_configuracao_e_auditada():
    configuracao = ConfiguracaoSistema.obter()
    configuracao.nome_propriedade = "Sítio Horizonte"
    configuracao.save()
    registro = RegistroAuditoria.objects.filter(
        modulo="core",
        entidade="configuracaosistema",
        identificador="1",
        operacao="alteracao",
    ).latest("data_hora")
    assert registro.dados_novos["nome_propriedade"] == "Sítio Horizonte"


@pytest.mark.django_db
def test_dashboard_exige_login(client):
    resposta = client.get(reverse("core:dashboard"))
    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


@pytest.mark.django_db
def test_dashboard_exibe_somente_as_acoes_essenciais(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="painel", password="segura123")
    client.force_login(usuario)

    resposta = client.get(reverse("core:dashboard"))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    for texto in (
        "Cadastrar animal",
        "Cadastrar bezerro",
        "Registrar cobertura",
        "Registrar leite",
        "Leite tirado hoje",
        "Leite neste mês",
    ):
        assert texto in conteudo
    for texto in ("Diagnóstico", "Destino", "Financeiro", "Medicamento", "Pesagem"):
        assert texto not in conteudo


@pytest.mark.django_db
def test_health_checks_nao_expoem_detalhes(client):
    for nome in ("health", "health_live", "health_ready"):
        resposta = client.get(reverse(nome))
        assert resposta.status_code == 200
        assert resposta.json() == {"status": "ok"}


def test_upload_rejeita_extensao_nao_permitida(settings):
    arquivo = SimpleUploadedFile("dados.exe", b"MZ", content_type="application/octet-stream")
    with pytest.raises(ValidationError):
        validar_upload_privado(arquivo)


def test_upload_aceita_pdf(settings):
    arquivo = SimpleUploadedFile("recibo.pdf", b"%PDF-1.4\n", content_type="application/pdf")
    validar_upload_privado(arquivo)


def test_upload_rejeita_conteudo_disfarcado_de_pdf(settings):
    arquivo = SimpleUploadedFile("recibo.pdf", b"MZ executavel", content_type="application/pdf")
    with pytest.raises(ValidationError):
        validar_upload_privado(arquivo)


def test_upload_rejeita_mime_incompativel_com_extensao(settings):
    arquivo = SimpleUploadedFile(
        "foto.jpg",
        b"\xff\xd8\xff\xe0imagem",
        content_type="image/png",
    )
    with pytest.raises(ValidationError):
        validar_upload_privado(arquivo)


def test_upload_de_foto_rejeita_pdf(settings):
    arquivo = SimpleUploadedFile("foto.pdf", b"%PDF-1.4\n", content_type="application/pdf")
    with pytest.raises(ValidationError):
        validar_upload_imagem(arquivo)
