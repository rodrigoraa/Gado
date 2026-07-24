from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.leite.models import DestinoLeite
from apps.rebanho.models import Animal

from ..models import ProdutoSaude, Tratamento
from ..selectors import tratamentos_em_carencia
from ..services import cancelar_tratamento, registrar_descarte_leite, salvar_tratamento

pytestmark = pytest.mark.django_db


def criar_vaca() -> Animal:
    return Animal.objects.create(
        identificacao="V-SA-01",
        sexo=Animal.Sexo.FEMEA,
        data_nascimento=timezone.localdate() - timedelta(days=800),
    )


def criar_produto() -> ProdutoSaude:
    return ProdutoSaude.objects.create(
        nome="Medicamento teste",
        tipo=ProdutoSaude.Tipo.MEDICAMENTO,
        fabricante="Laboratório teste",
        unidade="mL",
        carencia_padrao_dias=2,
        carencia_padrao_horas=6,
    )


def test_calcula_carencia_e_libera_no_horario_exato() -> None:
    vaca = criar_vaca()
    produto = criar_produto()
    aplicacao = timezone.now() - timedelta(hours=1)
    tratamento = salvar_tratamento(
        animal=vaca,
        produto=produto,
        data_hora=aplicacao,
        dose=Decimal("8.000"),
        motivo="Mastite",
    )
    assert tratamento.data_liberacao == aplicacao + timedelta(days=2, hours=6)
    assert tratamento.em_carencia
    assert tratamentos_em_carencia().filter(pk=tratamento.pk).exists()


def test_correcao_exige_justificativa() -> None:
    tratamento = salvar_tratamento(
        animal=criar_vaca(),
        produto=criar_produto(),
        data_hora=timezone.now() - timedelta(hours=1),
        dose=Decimal("5.000"),
        motivo="Tratamento",
    )
    with pytest.raises(ValidationError):
        salvar_tratamento(instancia=tratamento, dose=Decimal("6.000"))


def test_descarte_fica_ligado_ao_tratamento() -> None:
    tratamento = salvar_tratamento(
        animal=criar_vaca(),
        produto=criar_produto(),
        data_hora=timezone.now() - timedelta(hours=1),
        dose=Decimal("5.000"),
        motivo="Tratamento",
    )
    descarte = registrar_descarte_leite(
        tratamento=tratamento,
        quantidade_litros=Decimal("12.500"),
        observacoes="Leite separado e descartado.",
    )
    assert descarte.tipo == DestinoLeite.Tipo.DESCARTE
    assert descarte.tratamento == tratamento


def test_cancelamento_remove_alerta_sem_apagar_historico() -> None:
    tratamento = salvar_tratamento(
        animal=criar_vaca(),
        produto=criar_produto(),
        data_hora=timezone.now() - timedelta(hours=1),
        dose=Decimal("5.000"),
        motivo="Tratamento",
    )
    cancelar_tratamento(tratamento=tratamento, motivo="Aplicação lançada no animal errado.")
    tratamento.refresh_from_db()
    assert tratamento.situacao == Tratamento.Situacao.CANCELADO
    assert not tratamento.ativo_registro
    assert not tratamento.em_carencia


def test_rotas_de_saude_exigem_login(client) -> None:  # type: ignore[no-untyped-def]
    resposta = client.get(reverse("saude:tratamentos"))
    assert resposta.status_code == 302
    assert "/entrar/" in resposta.url


def test_cadastro_de_produto_permanece_no_formulario(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(
        username="produto-redirect",
        password="teste",
    )
    client.force_login(usuario)
    url = reverse("saude:produto_novo")

    resposta = client.post(
        url,
        {
            "nome": "Produto contínuo",
            "tipo": ProdutoSaude.Tipo.MEDICAMENTO,
            "fabricante": "",
            "unidade": "mL",
            "carencia_padrao_dias": "0",
            "carencia_padrao_horas": "0",
            "observacoes": "",
            "ativo": "on",
        },
    )

    assert resposta.status_code == 302
    assert resposta.url == url
    assert ProdutoSaude.objects.filter(nome="Produto contínuo").exists()
