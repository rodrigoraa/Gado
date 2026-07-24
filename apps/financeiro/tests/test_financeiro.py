from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.core.models import ArquivoAnexo

from ..forms import EntregaLeiteForm, LaticinioForm
from ..models import EntregaLeite, FechamentoLeite, Laticinio, RecebimentoLeite
from ..services import (
    cancelar_fechamento,
    criar_fechamento,
    finalizar_fechamento,
    registrar_recebimento,
    salvar_entrega,
    salvar_laticinio,
    salvar_preco,
)

pytestmark = pytest.mark.django_db


def criar_laticinio() -> Laticinio:
    return salvar_laticinio(
        razao_social="Laticínio Boa Vista Ltda.",
        nome_fantasia="Boa Vista",
        dia_fechamento=25,
        dia_pagamento=10,
        ativo=True,
    )


def criar_preco(laticinio: Laticinio, *, valor: str = "2.0000") -> None:
    salvar_preco(
        laticinio=laticinio,
        data_inicial=timezone.localdate() - timedelta(days=30),
        data_final=timezone.localdate(),
        valor_litro=Decimal(valor),
    )


def criar_entrega(laticinio: Laticinio) -> EntregaLeite:
    criar_preco(laticinio)
    return salvar_entrega(
        data_coleta=timezone.now() - timedelta(hours=1),
        quantidade_litros=Decimal("100.000"),
        bonificacao_qualidade=Decimal("10.00"),
        bonificacao_volume=Decimal("5.00"),
        outras_bonificacoes=Decimal("1.00"),
        desconto_qualidade=Decimal("2.00"),
        frete=Decimal("3.00"),
        taxas=Decimal("1.00"),
        outros_descontos=Decimal("4.00"),
    )


def test_troca_de_laticinio_ativo_exige_confirmacao() -> None:
    primeiro = criar_laticinio()
    with pytest.raises(ValidationError):
        salvar_laticinio(razao_social="Outro", ativo=True)
    segundo = salvar_laticinio(razao_social="Outro", ativo=True, confirmar_troca=True)
    primeiro.refresh_from_db()
    assert not primeiro.ativo
    assert segundo.ativo
    assert Laticinio.objects.filter(ativo=True).count() == 1


def test_formulario_confirma_troca_de_laticinio() -> None:
    primeiro = criar_laticinio()
    form = LaticinioForm(
        data={
            "razao_social": "Novo comprador",
            "dia_fechamento": 25,
            "dia_pagamento": 10,
            "ativo": "on",
            "confirmar_troca": "on",
        }
    )
    assert form.is_valid(), form.errors
    novo = form.save()
    primeiro.refresh_from_db()
    assert novo.ativo and not primeiro.ativo


def test_preco_nao_pode_sobrepor_periodo() -> None:
    laticinio = criar_laticinio()
    criar_preco(laticinio)
    with pytest.raises(ValidationError):
        salvar_preco(
            laticinio=laticinio,
            data_inicial=timezone.localdate() - timedelta(days=2),
            valor_litro=Decimal("2.1000"),
        )


def test_entrega_preserva_preco_e_recalcula_totais_no_backend() -> None:
    laticinio = criar_laticinio()
    entrega = criar_entrega(laticinio)
    salvar_preco(
        laticinio=laticinio,
        data_inicial=timezone.localdate() + timedelta(days=1),
        valor_litro=Decimal("3.0000"),
    )
    entrega.refresh_from_db()

    assert entrega.valor_litro == Decimal("2.0000")
    assert entrega.valor_bruto == Decimal("200.00")
    assert entrega.total_bonificacoes == Decimal("16.00")
    assert entrega.total_descontos == Decimal("10.00")
    assert entrega.valor_liquido == Decimal("206.00")


def test_formulario_entrega_aplica_preco_vigente_sem_expor_comprador() -> None:
    laticinio = criar_laticinio()
    criar_preco(laticinio)
    form = EntregaLeiteForm(
        data={
            "data_coleta": (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "quantidade_litros": "50.000",
            "bonificacao_qualidade": "0.00",
            "bonificacao_volume": "0.00",
            "outras_bonificacoes": "0.00",
            "desconto_qualidade": "0.00",
            "frete": "0.00",
            "taxas": "0.00",
            "outros_descontos": "0.00",
        }
    )
    assert "laticinio" not in form.fields
    assert form.is_valid(), form.errors
    entrega = form.save()
    assert entrega.laticinio == laticinio
    assert entrega.valor_litro == Decimal("2.0000")


def test_fechamento_pagamentos_parcial_total_e_excesso() -> None:
    laticinio = criar_laticinio()
    entrega = criar_entrega(laticinio)
    hoje = timezone.localdate()
    fechamento = criar_fechamento(
        entregas=[entrega],
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
        total_litros_informado=Decimal("100.000"),
        valor_liquido_informado=Decimal("206.00"),
    )
    assert fechamento.valor_liquido_calculado == Decimal("206.00")
    assert fechamento.situacao == FechamentoLeite.Situacao.FECHADO

    registrar_recebimento(
        fechamento=fechamento,
        data=hoje,
        valor=Decimal("100.00"),
        forma_pagamento=RecebimentoLeite.FormaPagamento.PIX,
    )
    fechamento.refresh_from_db()
    assert fechamento.situacao == FechamentoLeite.Situacao.PARCIALMENTE_PAGO
    assert fechamento.saldo == Decimal("106.00")

    registrar_recebimento(
        fechamento=fechamento,
        data=hoje,
        valor=Decimal("106.00"),
        forma_pagamento=RecebimentoLeite.FormaPagamento.TRANSFERENCIA,
    )
    fechamento.refresh_from_db()
    assert fechamento.situacao == FechamentoLeite.Situacao.PAGO
    assert fechamento.saldo == Decimal("0.00")
    entrega.refresh_from_db()
    assert entrega.situacao == EntregaLeite.Situacao.PAGA
    assert entrega.data_pagamento_integral == hoje

    with pytest.raises(ValidationError):
        registrar_recebimento(
            fechamento=fechamento,
            data=hoje,
            valor=Decimal("5.00"),
            forma_pagamento=RecebimentoLeite.FormaPagamento.PIX,
        )


def test_cancelamento_do_fechamento_libera_entrega() -> None:
    laticinio = criar_laticinio()
    entrega = criar_entrega(laticinio)
    hoje = timezone.localdate()
    fechamento = criar_fechamento(
        entregas=[entrega],
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
    )
    cancelar_fechamento(fechamento=fechamento, motivo="Demonstrativo emitido incorretamente.")
    entrega.refresh_from_db()
    fechamento.refresh_from_db()
    assert fechamento.situacao == FechamentoLeite.Situacao.CANCELADO
    assert not fechamento.ativo_registro
    assert entrega.situacao == EntregaLeite.Situacao.AGUARDANDO_FECHAMENTO


def test_finaliza_fechamento_aberto_e_transiciona_entregas() -> None:
    laticinio = criar_laticinio()
    entrega = criar_entrega(laticinio)
    hoje = timezone.localdate()
    fechamento = criar_fechamento(
        entregas=[entrega],
        finalizar=False,
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
        total_litros_informado=Decimal("100.000"),
        valor_liquido_informado=Decimal("206.00"),
    )
    entrega.refresh_from_db()
    assert fechamento.situacao == FechamentoLeite.Situacao.ABERTO
    assert entrega.situacao == EntregaLeite.Situacao.AGUARDANDO_FECHAMENTO

    finalizado = finalizar_fechamento(fechamento=fechamento)
    entrega.refresh_from_db()
    assert finalizado.situacao == FechamentoLeite.Situacao.FECHADO
    assert finalizado.valor_liquido_calculado == Decimal("206.00")
    assert entrega.situacao == EntregaLeite.Situacao.FECHADA


def test_interface_finaliza_fechamento_aberto(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    entrega = criar_entrega(criar_laticinio())
    hoje = timezone.localdate()
    fechamento = criar_fechamento(
        entregas=[entrega],
        finalizar=False,
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
    )
    usuario = django_user_model.objects.create_user(
        username="finalizador", password="senha-forte-123"
    )
    client.force_login(usuario)
    url = reverse("financeiro:fechamento_finalizar", args=(fechamento.pk,))

    assert client.get(url).status_code == 200
    resposta = client.post(url)

    assert resposta.status_code == 302
    fechamento.refresh_from_db()
    entrega.refresh_from_db()
    assert fechamento.situacao == FechamentoLeite.Situacao.FECHADO
    assert entrega.situacao == EntregaLeite.Situacao.FECHADA


def test_fechamento_aceita_entrega_de_laticinio_historico_inativo() -> None:
    laticinio_anterior = criar_laticinio()
    entrega_historica = criar_entrega(laticinio_anterior)
    salvar_laticinio(
        razao_social="Novo laticínio ativo",
        ativo=True,
        confirmar_troca=True,
    )
    hoje = timezone.localdate()

    fechamento = criar_fechamento(
        entregas=[entrega_historica],
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
    )

    laticinio_anterior.refresh_from_db()
    assert not laticinio_anterior.ativo
    assert fechamento.laticinio == laticinio_anterior
    assert fechamento.situacao == FechamentoLeite.Situacao.FECHADO


def test_fechamento_rejeita_entregas_de_laticinios_diferentes() -> None:
    primeiro = criar_laticinio()
    entrega_primeiro = criar_entrega(primeiro)
    segundo = salvar_laticinio(
        razao_social="Segundo laticínio",
        ativo=True,
        confirmar_troca=True,
    )
    criar_preco(segundo)
    entrega_segundo = salvar_entrega(
        data_coleta=timezone.now() - timedelta(minutes=30),
        quantidade_litros=Decimal("50.000"),
    )
    hoje = timezone.localdate()

    with pytest.raises(ValidationError, match="mesmo laticínio"):
        criar_fechamento(
            entregas=[entrega_primeiro, entrega_segundo],
            competencia=date(hoje.year, hoje.month, 1),
            data_inicial=date(hoje.year, hoje.month, 1),
            data_final=hoje,
        )


def test_transicoes_individuais_de_laticinio_e_entrega_sao_auditadas() -> None:
    primeiro = criar_laticinio()
    entrega = criar_entrega(primeiro)
    salvar_laticinio(
        razao_social="Comprador substituto",
        ativo=True,
        confirmar_troca=True,
    )
    primeiro.refresh_from_db()
    auditoria_laticinio = (
        RegistroAuditoria.objects.filter(
            modulo="financeiro",
            entidade="laticinio",
            identificador=str(primeiro.pk),
            operacao="alteracao",
        )
        .order_by("-data_hora")
        .first()
    )
    assert auditoria_laticinio is not None
    assert auditoria_laticinio.dados_novos["ativo"] is False

    hoje = timezone.localdate()
    criar_fechamento(
        entregas=[entrega],
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
    )
    auditoria_entrega = (
        RegistroAuditoria.objects.filter(
            modulo="financeiro",
            entidade="entregaleite",
            identificador=str(entrega.pk),
            operacao="alteracao",
        )
        .order_by("-data_hora")
        .first()
    )
    assert auditoria_entrega is not None
    assert auditoria_entrega.dados_novos["situacao"] == EntregaLeite.Situacao.FECHADA


def test_rotas_financeiras_exigem_login(client) -> None:  # type: ignore[no-untyped-def]
    resposta = client.get(reverse("financeiro:entregas"))
    assert resposta.status_code == 302
    assert "/entrar/" in resposta.url


def test_download_financeiro_autenticado_nao_pode_ser_armazenado_em_cache(
    client, django_user_model, settings, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = tmp_path
    entrega = criar_entrega(criar_laticinio())
    entrega.anexo.save(
        "comprovante.pdf",
        SimpleUploadedFile("comprovante.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf"),
    )
    url = reverse("financeiro:arquivo_privado", args=("entrega", entrega.pk))
    resposta_anonima = client.get(url)
    assert resposta_anonima.status_code == 302
    assert "/entrar/" in resposta_anonima.url

    usuario = django_user_model.objects.create_user(
        username="financeiro-download", password="senha-forte-123"
    )
    client.force_login(usuario)

    resposta = client.get(url)

    assert resposta.status_code == 200
    assert resposta["Cache-Control"] == "private, no-store"
    resposta.close()


def test_uploads_financeiros_registram_metadados_obrigatorios(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = tmp_path
    laticinio = criar_laticinio()
    criar_preco(laticinio)
    anexo_entrega = SimpleUploadedFile(
        "romaneio-original.pdf",
        b"%PDF-1.4\n%%EOF\n",
        "application/pdf",
    )
    entrega = salvar_entrega(
        data_coleta=timezone.now() - timedelta(hours=1),
        quantidade_litros=Decimal("100.000"),
        anexo=anexo_entrega,
    )
    hoje = timezone.localdate()
    demonstrativo = SimpleUploadedFile(
        "demonstrativo.pdf",
        b"%PDF-1.4\n%%EOF\n",
        "application/pdf",
    )
    fechamento = criar_fechamento(
        entregas=[entrega],
        competencia=date(hoje.year, hoje.month, 1),
        data_inicial=date(hoje.year, hoje.month, 1),
        data_final=hoje,
        arquivo_demonstrativo=demonstrativo,
    )
    comprovante = SimpleUploadedFile(
        "comprovante.pdf",
        b"%PDF-1.4\n%%EOF\n",
        "application/pdf",
    )
    recebimento = registrar_recebimento(
        fechamento=fechamento,
        data=hoje,
        valor=fechamento.valor_liquido_calculado,
        forma_pagamento=RecebimentoLeite.FormaPagamento.PIX,
        anexo=comprovante,
    )

    metadados = ArquivoAnexo.objects.filter(ativo=True)
    assert metadados.filter(object_id=str(entrega.pk), campo="anexo").exists()
    assert metadados.filter(object_id=str(fechamento.pk), campo="arquivo_demonstrativo").exists()
    recebido = metadados.get(object_id=str(recebimento.pk), campo="anexo")
    assert recebido.nome_original == "comprovante.pdf"
    assert recebido.mime_type == "application/pdf"
    assert recebido.tamanho_bytes == len(comprovante)


def test_cadastro_de_laticinio_permanece_no_formulario(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(
        username="laticinio-redirect",
        password="teste",
    )
    client.force_login(usuario)
    url = reverse("financeiro:laticinio_novo")

    resposta = client.post(
        url,
        {
            "razao_social": "Comprador contínuo",
            "nome_fantasia": "",
            "cpf_cnpj": "",
            "telefone": "",
            "email": "",
            "endereco": "",
            "codigo_produtor": "",
            "dia_fechamento": "30",
            "dia_pagamento": "10",
            "observacoes": "",
            "ativo": "on",
        },
    )

    assert resposta.status_code == 302
    assert resposta.url == url
    assert Laticinio.objects.filter(razao_social="Comprador contínuo").exists()
