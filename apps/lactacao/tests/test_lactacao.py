from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.lactacao.models import Lactacao
from apps.lactacao.selectors import indicadores_lactacao, lactacoes_ativas
from apps.lactacao.services import encerrar_lactacao, iniciar_lactacao, secar_lactacao
from apps.leite.models import Ordenha, ProducaoAnimal
from apps.rebanho.models import Animal
from apps.rebanho.services import salvar_animal
from apps.reproducao.models import Nascimento, Parto
from apps.reproducao.services import registrar_parto

pytestmark = pytest.mark.django_db


@pytest.fixture
def vaca() -> Animal:
    return salvar_animal(
        identificacao="V-LACT",
        sexo=Animal.Sexo.FEMEA,
        data_nascimento=timezone.localdate() - timedelta(days=365 * 4),
    )


def criar_parto(vaca: Animal, *, dias_atras: int) -> Parto:
    return registrar_parto(
        vaca=vaca,
        data_hora=timezone.now() - timedelta(days=dias_atras),
        resultado=Parto.Resultado.NORMAL,
        bezerros=[
            {
                "identificacao": f"B-LACT-{Parto.objects.count() + 1}",
                "sexo": Animal.Sexo.FEMEA,
                "situacao": Nascimento.Situacao.VIVO,
            }
        ],
    )


def test_inicia_com_ordem_automatica_e_impede_duas_ativas(vaca: Animal) -> None:
    parto = criar_parto(vaca, dias_atras=10)
    primeira = iniciar_lactacao(
        vaca=vaca,
        parto=parto,
        data_inicio=timezone.localdate() - timedelta(days=10),
    )
    assert primeira.ordem == 1
    assert primeira.situacao == Lactacao.Situacao.ATIVA
    with pytest.raises(ValidationError, match="já possui"):
        iniciar_lactacao(vaca=vaca, parto=parto, data_inicio=timezone.localdate())


def test_nao_inicia_lactacao_para_macho() -> None:
    macho = salvar_animal(
        identificacao="M-LACT",
        sexo=Animal.Sexo.MACHO,
        data_nascimento=timezone.localdate() - timedelta(days=365 * 3),
    )
    with pytest.raises(ValidationError, match="fêmea"):
        iniciar_lactacao(vaca=macho, data_inicio=timezone.localdate())


def test_fluxo_normal_exige_parto(vaca: Animal) -> None:
    with pytest.raises(ValidationError, match="parto"):
        iniciar_lactacao(vaca=vaca, data_inicio=timezone.localdate())


def test_dias_em_lactacao(vaca: Animal) -> None:
    parto = criar_parto(vaca, dias_atras=20)
    lactacao = iniciar_lactacao(
        vaca=vaca,
        parto=parto,
        data_inicio=timezone.localdate() - timedelta(days=20),
    )
    assert lactacao.dias_em_lactacao == 20


def test_secagem_remove_vaca_da_ordenha(vaca: Animal) -> None:
    parto = criar_parto(vaca, dias_atras=100)
    lactacao = iniciar_lactacao(
        vaca=vaca,
        parto=parto,
        data_inicio=timezone.localdate() - timedelta(days=100),
    )
    secar_lactacao(lactacao=lactacao, data_secagem=timezone.localdate())
    lactacao.refresh_from_db()
    assert lactacao.situacao == Lactacao.Situacao.SECA
    assert lactacao.data_secagem == timezone.localdate()
    assert not lactacoes_ativas().filter(pk=lactacao.pk).exists()


def test_encerramento_preserva_lactacao(vaca: Animal) -> None:
    parto = criar_parto(vaca, dias_atras=20)
    lactacao = iniciar_lactacao(
        vaca=vaca,
        parto=parto,
        data_inicio=timezone.localdate() - timedelta(days=20),
    )
    encerrar_lactacao(lactacao=lactacao, data_encerramento=timezone.localdate() - timedelta(days=1))
    lactacao.refresh_from_db()
    assert lactacao.situacao == Lactacao.Situacao.ENCERRADA
    assert lactacao.dias_em_lactacao == 19


def test_indicadores_somam_producao_e_medias(vaca: Animal) -> None:
    parto = criar_parto(vaca, dias_atras=10)
    lactacao = iniciar_lactacao(
        vaca=vaca,
        parto=parto,
        data_inicio=timezone.localdate() - timedelta(days=10),
    )
    manha = Ordenha.objects.create(
        data=timezone.localdate() - timedelta(days=1),
        periodo=Ordenha.Periodo.MANHA,
        modo=Ordenha.Modo.INDIVIDUAL,
        quantidade_total=Decimal("12.000"),
        quantidade_vacas=1,
    )
    tarde = Ordenha.objects.create(
        data=timezone.localdate(),
        periodo=Ordenha.Periodo.TARDE,
        modo=Ordenha.Modo.INDIVIDUAL,
        quantidade_total=Decimal("8.000"),
        quantidade_vacas=1,
    )
    ProducaoAnimal.objects.create(
        ordenha=manha,
        vaca=vaca,
        lactacao=lactacao,
        quantidade_litros=Decimal("12.000"),
    )
    ProducaoAnimal.objects.create(
        ordenha=tarde,
        vaca=vaca,
        lactacao=lactacao,
        quantidade_litros=Decimal("8.000"),
    )
    indicadores = indicadores_lactacao(lactacao=lactacao)
    assert indicadores.producao_acumulada == Decimal("20.000")
    assert indicadores.media_diaria == Decimal("10.000")
    assert indicadores.maior_producao_diaria == Decimal("12.000")
    assert indicadores.menor_producao_diaria == Decimal("8.000")
    assert indicadores.dias_com_registro == 2


def test_telas_de_lactacao_renderizam_autenticadas(client, django_user_model, vaca: Animal) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="lactacao", password="teste")
    client.force_login(usuario)
    parto = criar_parto(vaca, dias_atras=3)
    lactacao = iniciar_lactacao(
        vaca=vaca,
        parto=parto,
        data_inicio=timezone.localdate() - timedelta(days=3),
    )
    assert client.get(reverse("lactacao:lista")).status_code == 200
    assert (
        client.get(reverse("lactacao:detalhe", kwargs={"lactacao_id": lactacao.pk})).status_code
        == 200
    )
