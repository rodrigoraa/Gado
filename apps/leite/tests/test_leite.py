from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.core.alertas import verificar_queda_producao
from apps.lactacao.models import Lactacao
from apps.rebanho.models import Animal
from apps.saude.models import ProdutoSaude
from apps.saude.services import salvar_tratamento

from ..forms import OrdenhaForm
from ..models import DestinoLeite, Ordenha
from ..selectors import conciliacao_dia, detectar_quedas_producao, resumo_mensal
from ..services import (
    cancelar_ordenha,
    conciliar_ordenha,
    registrar_producao,
    salvar_destino,
    salvar_ordenha,
    vaca_em_carencia,
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


def criar_lactacao(vaca: Animal) -> Lactacao:
    return Lactacao.objects.create(
        vaca=vaca,
        ordem=1,
        data_inicio=timezone.localdate() - timedelta(days=30),
        situacao=Lactacao.Situacao.ATIVA,
    )


def test_ordenha_soma_individual_e_exige_justificativa_para_divergencia() -> None:
    vaca = criar_vaca()
    criar_lactacao(vaca)
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
    with pytest.raises(ValidationError):
        conciliar_ordenha(ordenha=ordenha)
    conciliada = conciliar_ordenha(ordenha=ordenha, justificativa="Medição do tanque conferida.")
    assert conciliada.justificativa_divergencia


def test_mes_soma_ordenha_uma_vez_mesmo_com_varias_vacas() -> None:
    vaca_a = criar_vaca(identificacao="V-010")
    vaca_b = criar_vaca(identificacao="V-011")
    criar_lactacao(vaca_a)
    criar_lactacao(vaca_b)
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


def test_alerta_carencia_na_ordenha() -> None:
    vaca = criar_vaca(identificacao="V-020")
    produto = ProdutoSaude.objects.create(
        nome="Antibiótico teste",
        tipo=ProdutoSaude.Tipo.MEDICAMENTO,
        unidade="mL",
        carencia_padrao_dias=3,
    )
    salvar_tratamento(
        animal=vaca,
        produto=produto,
        data_hora=timezone.now() - timedelta(hours=1),
        dose=Decimal("10.000"),
        motivo="Tratamento clínico",
    )
    assert vaca_em_carencia(vaca=vaca)


def test_carencia_sem_horario_considera_todo_o_dia_da_ordenha() -> None:
    vaca = criar_vaca(identificacao="V-021")
    produto = ProdutoSaude.objects.create(
        nome="Antibiótico com liberação ao meio-dia",
        tipo=ProdutoSaude.Tipo.MEDICAMENTO,
        unidade="mL",
        carencia_padrao_dias=1,
    )
    hoje = timezone.localdate()
    liberacao = timezone.make_aware(
        datetime.combine(hoje, time(12, 0)),
        timezone.get_current_timezone(),
    )
    salvar_tratamento(
        animal=vaca,
        produto=produto,
        data_hora=liberacao - timedelta(days=1),
        dose=Decimal("10.000"),
        motivo="Tratamento clínico",
    )
    ordenha = salvar_ordenha(
        data=hoje,
        periodo=Ordenha.Periodo.MANHA,
        horario=None,
        quantidade_total=Decimal("10.000"),
        quantidade_vacas=1,
    )

    assert vaca_em_carencia(vaca=vaca, ordenha=ordenha)
    assert not vaca_em_carencia(
        vaca=vaca,
        ordenha=ordenha,
        momento=liberacao + timedelta(hours=1),
    )


def test_producao_rejeita_animal_inativo_mesmo_com_lactacao_ativa() -> None:
    vaca = criar_vaca(identificacao="V-022")
    criar_lactacao(vaca)
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


def test_producao_rejeita_ordenha_anterior_ao_inicio_da_lactacao() -> None:
    vaca = criar_vaca(identificacao="V-023")
    Lactacao.objects.create(
        vaca=vaca,
        ordem=1,
        data_inicio=timezone.localdate(),
        situacao=Lactacao.Situacao.ATIVA,
    )
    ordenha = salvar_ordenha(
        data=timezone.localdate() - timedelta(days=1),
        periodo=Ordenha.Periodo.MANHA,
        quantidade_total=Decimal("10.000"),
        quantidade_vacas=1,
    )

    with pytest.raises(ValidationError, match="anteceder o início"):
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


def test_queda_producao_ignora_ordenhas_canceladas() -> None:
    vaca = criar_vaca(identificacao="V-024")
    criar_lactacao(vaca)
    referencia = timezone.localdate()
    for dias_atras in (10, 9, 8, 7):
        ordenha = salvar_ordenha(
            data=referencia - timedelta(days=dias_atras),
            periodo=Ordenha.Periodo.MANHA,
            modo=Ordenha.Modo.INDIVIDUAL,
            quantidade_total=Decimal("20.000"),
            quantidade_vacas=1,
        )
        registrar_producao(
            ordenha=ordenha,
            vaca=vaca,
            quantidade_litros=Decimal("20.000"),
        )
        cancelar_ordenha(ordenha=ordenha, motivo="Ordenha lançada em duplicidade")
    for dias_atras in (3, 2):
        ordenha = salvar_ordenha(
            data=referencia - timedelta(days=dias_atras),
            periodo=Ordenha.Periodo.MANHA,
            modo=Ordenha.Modo.INDIVIDUAL,
            quantidade_total=Decimal("5.000"),
            quantidade_vacas=1,
        )
        registrar_producao(
            ordenha=ordenha,
            vaca=vaca,
            quantidade_litros=Decimal("5.000"),
        )

    assert detectar_quedas_producao(data_referencia=referencia) == []
    assert verificar_queda_producao() == 0


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
