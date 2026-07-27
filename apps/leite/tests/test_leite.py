from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.rebanho.models import Animal

from ..forms import OrdenhaForm
from ..models import DestinoLeite, Ordenha
from ..selectors import conciliacao_dia, resumo_mensal
from ..services import (
    cancelar_ordenha,
    conciliar_ordenha,
    registrar_producao,
    salvar_destino,
    salvar_ordenha,
)

pytestmark = pytest.mark.django_db


def test_formulario_de_leite_tem_data_turno_e_litros() -> None:
    formulario = OrdenhaForm()

    assert list(formulario.fields) == ["data", "periodo", "quantidade_total"]
    assert list(formulario.fields["periodo"].choices) == [
        (Ordenha.Periodo.MANHA, "Matutino"),
        (Ordenha.Periodo.TARDE, "Vespertino"),
        (Ordenha.Periodo.OUTRO, "2 Turnos"),
    ]
    assert formulario["periodo"].value() == Ordenha.Periodo.OUTRO


def test_formulario_registra_total_dos_dois_turnos() -> None:
    formulario = OrdenhaForm(
        data={
            "data": timezone.localdate().isoformat(),
            "periodo": Ordenha.Periodo.OUTRO,
            "quantidade_total": "35.500",
        }
    )

    assert formulario.is_valid(), formulario.errors
    ordenha = formulario.save()
    assert ordenha.periodo == Ordenha.Periodo.OUTRO
    assert ordenha.quantidade_total == Decimal("35.500")
    assert str(ordenha).startswith("2 Turnos")


def test_cadastro_de_leite_redireciona_para_o_detalhe(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="leite-redirect", password="teste")
    client.force_login(usuario)

    resposta = client.post(
        reverse("leite:ordenha_nova"),
        {
            "data": timezone.localdate().isoformat(),
            "periodo": Ordenha.Periodo.OUTRO,
            "quantidade_total": "35.500",
        },
    )

    assert resposta.status_code == 302
    assert resposta.url == reverse("leite:ordenha_nova")
    assert Ordenha.objects.filter(quantidade_total=Decimal("35.500")).exists()


def test_total_de_dois_turnos_nao_pode_ser_misturado_com_turno_separado() -> None:
    hoje = timezone.localdate()
    salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.OUTRO,
        quantidade_total=Decimal("35.500"),
        quantidade_vacas=0,
    )

    with pytest.raises(ValidationError, match="2 Turnos"):
        salvar_ordenha(
            data=hoje,
            periodo=Ordenha.Periodo.MANHA,
            quantidade_total=Decimal("18.000"),
            quantidade_vacas=0,
        )


def test_turnos_separados_formam_o_total_do_dia() -> None:
    hoje = timezone.localdate()
    salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.MANHA,
        quantidade_total=Decimal("18.000"),
        quantidade_vacas=0,
    )
    salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.TARDE,
        quantidade_total=Decimal("17.500"),
        quantidade_vacas=0,
    )

    resumo = resumo_mensal(ano=hoje.year, mes=hoje.month)
    assert resumo["total"] == Decimal("35.500")


def criar_vaca(*, identificacao: str = "V-001") -> Animal:
    return Animal.objects.create(
        identificacao=identificacao,
        sexo=Animal.Sexo.FEMEA,
        data_nascimento=timezone.localdate() - timedelta(days=900),
    )


def test_ordenha_soma_individual_e_registra_divergencia_automaticamente() -> None:
    vaca = criar_vaca()
    ordenha = salvar_ordenha(
        data=timezone.localdate(),
        periodo=Ordenha.Periodo.MANHA,
        modo=Ordenha.Modo.INDIVIDUAL,
        quantidade_total=Decimal("10.000"),
        quantidade_vacas=0,
    )
    registrar_producao(ordenha=ordenha, vaca=vaca, quantidade_litros=Decimal("8.500"))
    ordenha.refresh_from_db()

    assert ordenha.quantidade_vacas == 1
    assert ordenha.total_individual == Decimal("8.500")
    assert ordenha.diferenca_individual == Decimal("1.500")
    conciliada = conciliar_ordenha(ordenha=ordenha)
    assert conciliada.justificativa_divergencia == (
        "Alteração registrada automaticamente pelo sistema."
    )


def test_mes_soma_ordenha_uma_vez_mesmo_com_varias_vacas() -> None:
    vaca_a = criar_vaca(identificacao="V-010")
    vaca_b = criar_vaca(identificacao="V-011")
    hoje = timezone.localdate()
    ordenha = salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.TARDE,
        modo=Ordenha.Modo.INDIVIDUAL,
        quantidade_total=Decimal("20.000"),
        quantidade_vacas=2,
    )
    registrar_producao(ordenha=ordenha, vaca=vaca_a, quantidade_litros=Decimal("9.000"))
    registrar_producao(ordenha=ordenha, vaca=vaca_b, quantidade_litros=Decimal("11.000"))

    resumo = resumo_mensal(ano=hoje.year, mes=hoje.month)
    assert resumo["total"] == Decimal("20.000")
    assert resumo["vacas"] == 2


def test_destino_concilia_com_total_produzido() -> None:
    hoje = timezone.localdate()
    salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.NOITE,
        quantidade_total=Decimal("12.500"),
        quantidade_vacas=2,
    )
    salvar_destino(
        data=hoje,
        tipo=DestinoLeite.Tipo.LATICINIO,
        quantidade_litros=Decimal("10.000"),
    )
    salvar_destino(
        data=hoje,
        tipo=DestinoLeite.Tipo.CONSUMO,
        quantidade_litros=Decimal("2.500"),
    )
    assert conciliacao_dia(dia=hoje)["diferenca"] == Decimal("0.000")


def test_producao_rejeita_animal_inativo() -> None:
    vaca = criar_vaca(identificacao="V-022")
    vaca.situacao = Animal.Situacao.MORTO
    vaca.data_saida = timezone.localdate()
    vaca.motivo_saida = "Óbito registrado"
    vaca.save(update_fields=("situacao", "data_saida", "motivo_saida", "atualizado_em"))
    ordenha = salvar_ordenha(
        data=timezone.localdate(),
        periodo=Ordenha.Periodo.MANHA,
        quantidade_total=Decimal("10.000"),
        quantidade_vacas=1,
    )

    with pytest.raises(ValidationError, match="animal ativo"):
        registrar_producao(
            ordenha=ordenha,
            vaca=vaca,
            quantidade_litros=Decimal("10.000"),
        )


def test_cancelamento_ordenha_bloqueia_destino_vinculado() -> None:
    hoje = timezone.localdate()
    ordenha = salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.TARDE,
        quantidade_total=Decimal("10.000"),
        quantidade_vacas=1,
    )
    salvar_destino(
        data=hoje,
        ordenha=ordenha,
        tipo=DestinoLeite.Tipo.CONSUMO,
        quantidade_litros=Decimal("10.000"),
    )

    with pytest.raises(ValidationError, match="destinos vinculados"):
        cancelar_ordenha(ordenha=ordenha, motivo="Lançamento incorreto")
    ordenha.refresh_from_db()
    assert ordenha.situacao == Ordenha.Situacao.REGISTRADA
    assert ordenha.ativo_registro


def test_rotas_de_leite_exigem_login(client) -> None:  # type: ignore[no-untyped-def]
    resposta = client.get(reverse("leite:ordenhas"))
    assert resposta.status_code == 302
    assert "/entrar/" in resposta.url


def test_filtro_ordenhas_entrega_partial_htmx(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="operador", password="segredo-forte")
    client.force_login(usuario)

    pagina = client.get(reverse("leite:ordenhas"))
    assert b'hx-get="/leite/ordenhas/"' in pagina.content

    partial = client.get(
        reverse("leite:ordenhas"),
        {"data_inicial": timezone.localdate().isoformat()},
        HTTP_HX_REQUEST="true",
    )
    assert partial.status_code == 200
    assert b'id="lista-registros"' in partial.content
    assert b"<!doctype html>" not in partial.content.lower()
