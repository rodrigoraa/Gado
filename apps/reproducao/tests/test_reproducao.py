from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.rebanho.models import Animal
from apps.rebanho.services import salvar_animal
from apps.reproducao.forms import CoberturaForm
from apps.reproducao.models import (
    Cobertura,
    DiagnosticoGestacao,
    Nascimento,
    Parto,
    PerdaGestacional,
)
from apps.reproducao.services import (
    TRATAMENTO_MANTER,
    alterar_data_cobertura,
    cancelar_cobertura,
    cancelar_parto,
    corrigir_parto,
    registrar_cobertura,
    registrar_diagnostico,
    registrar_parto,
    registrar_perda_gestacional,
)

pytestmark = pytest.mark.django_db


def test_formulario_de_cobertura_tem_apenas_vaca_boi_e_data() -> None:
    formulario = CoberturaForm()

    assert list(formulario.fields) == ["vaca", "touro", "data"]
    assert formulario.fields["touro"].required is False


@pytest.fixture
def vaca() -> Animal:
    return salvar_animal(
        identificacao="V-REPRO",
        sexo=Animal.Sexo.FEMEA,
        data_nascimento=timezone.localdate() - timedelta(days=365 * 4),
    )


@pytest.fixture
def touro() -> Animal:
    return salvar_animal(
        identificacao="T-REPRO",
        sexo=Animal.Sexo.MACHO,
        data_nascimento=timezone.localdate() - timedelta(days=365 * 5),
    )


def criar_cobertura(vaca: Animal, touro: Animal | None = None, **alteracoes) -> Cobertura:  # type: ignore[no-untyped-def]
    dados = {
        "vaca": vaca,
        "touro": touro,
        "data_cobertura": timezone.localdate() - timedelta(days=60),
        "tipo": Cobertura.Tipo.MONTA_NATURAL,
        "forma_identificacao": Cobertura.FormaIdentificacao.OBSERVADA,
    }
    dados.update(alteracoes)
    return registrar_cobertura(**dados)


def test_previsao_e_intervalo_sao_calculados(vaca: Animal, touro: Animal) -> None:
    data = timezone.localdate() - timedelta(days=30)
    cobertura = criar_cobertura(vaca, touro, data_cobertura=data)
    assert cobertura.previsao_original_parto == data + timedelta(days=283)
    assert cobertura.previsao_atual_parto == cobertura.previsao_original_parto
    assert cobertura.inicio_intervalo_parto == cobertura.previsao_atual_parto - timedelta(days=7)
    assert cobertura.fim_intervalo_parto == cobertura.previsao_atual_parto + timedelta(days=7)


def test_nova_cobertura_preserva_e_substitui_anterior(vaca: Animal) -> None:
    anterior = criar_cobertura(vaca)
    nova = criar_cobertura(vaca, data_cobertura=timezone.localdate() - timedelta(days=5))
    anterior.refresh_from_db()
    assert anterior.situacao == Cobertura.Situacao.SUBSTITUIDA
    assert nova.situacao == Cobertura.Situacao.REGISTRADA
    assert anterior.historico.filter(evento="NOVA_COBERTURA").exists()


def test_pode_manter_duas_coberturas_abertas(vaca: Animal) -> None:
    primeira = criar_cobertura(vaca)
    criar_cobertura(
        vaca,
        data_cobertura=timezone.localdate() - timedelta(days=3),
        tratamento_cobertura_aberta=TRATAMENTO_MANTER,
    )
    primeira.refresh_from_db()
    assert primeira.esta_aberta


def test_diagnostico_positivo_confirma_e_atualiza_previsao(vaca: Animal) -> None:
    cobertura = criar_cobertura(vaca)
    nova_previsao = timezone.localdate() + timedelta(days=180)
    registrar_diagnostico(
        cobertura=cobertura,
        data_diagnostico=timezone.localdate(),
        resultado=DiagnosticoGestacao.Resultado.PRENHE,
        metodo=DiagnosticoGestacao.Metodo.ULTRASSOM,
        nova_previsao_parto=nova_previsao,
    )
    cobertura.refresh_from_db()
    assert cobertura.situacao == Cobertura.Situacao.PRENHEZ_CONFIRMADA
    assert cobertura.previsao_atual_parto == nova_previsao
    assert cobertura.previsao_original_parto != nova_previsao


def test_diagnostico_negativo_encerra_sem_prenhez(vaca: Animal) -> None:
    cobertura = criar_cobertura(vaca)
    registrar_diagnostico(
        cobertura=cobertura,
        data_diagnostico=timezone.localdate(),
        resultado=DiagnosticoGestacao.Resultado.VAZIA,
        metodo=DiagnosticoGestacao.Metodo.PALPACAO,
    )
    cobertura.refresh_from_db()
    assert cobertura.situacao == Cobertura.Situacao.NAO_EMPRENHOU
    assert not cobertura.esta_aberta


def test_correcao_de_data_preserva_previsao_original_e_registra_historico(
    vaca: Animal,
) -> None:
    cobertura = criar_cobertura(vaca)
    data_original = cobertura.data
    previsao_original = cobertura.previsao_original_parto
    nova_data = data_original + timedelta(days=2)
    alterar_data_cobertura(
        cobertura=cobertura,
        nova_data=nova_data,
        justificativa="Data confirmada na agenda",
    )
    cobertura.refresh_from_db()
    assert cobertura.data_original == data_original
    assert cobertura.previsao_original_parto == previsao_original
    assert cobertura.previsao_atual_parto == nova_data + timedelta(days=283)
    assert cobertura.historico.filter(evento="ALTERACAO_DATA").exists()


def test_cancelamento_de_cobertura_exige_justificativa(vaca: Animal) -> None:
    cobertura = criar_cobertura(vaca)
    with pytest.raises(ValidationError, match="justificativa"):
        cancelar_cobertura(cobertura=cobertura, justificativa="")


def test_perda_gestacional_preserva_registro_e_encerra(vaca: Animal) -> None:
    cobertura = criar_cobertura(vaca)
    perda = registrar_perda_gestacional(
        cobertura=cobertura,
        data_perda=timezone.localdate(),
        tipo=PerdaGestacional.Tipo.ABORTO,
        observacoes="Ocorrência observada",
    )
    cobertura.refresh_from_db()
    assert perda.cobertura == cobertura
    assert cobertura.situacao == Cobertura.Situacao.PERDA_GESTACIONAL


def test_parto_atomico_cria_gemeos_e_relaciona_pais(vaca: Animal, touro: Animal) -> None:
    cobertura = criar_cobertura(
        vaca,
        touro,
        data_cobertura=timezone.localdate() - timedelta(days=283),
    )
    parto = registrar_parto(
        vaca=vaca,
        cobertura=cobertura,
        data_hora=timezone.now() - timedelta(minutes=1),
        resultado=Parto.Resultado.NORMAL,
        bezerros=[
            {
                "identificacao": "GEM-1",
                "sexo": Animal.Sexo.FEMEA,
                "situacao": Nascimento.Situacao.VIVO,
            },
            {
                "identificacao": "GEM-2",
                "sexo": Animal.Sexo.MACHO,
                "situacao": Nascimento.Situacao.VIVO,
            },
        ],
    )
    assert parto.quantidade_bezerros == 2
    filhos = Animal.objects.filter(mae=vaca, pai=touro, nascimento__parto=parto)
    assert filhos.count() == 2
    cobertura.refresh_from_db()
    assert cobertura.situacao == Cobertura.Situacao.FINALIZADA_COM_PARTO


def test_parto_aceita_pai_desconhecido(vaca: Animal) -> None:
    parto = registrar_parto(
        vaca=vaca,
        data_hora=timezone.now() - timedelta(minutes=1),
        resultado=Parto.Resultado.NORMAL,
        bezerros=[
            {
                "identificacao": "SEM-PAI",
                "sexo": Animal.Sexo.FEMEA,
                "situacao": Nascimento.Situacao.VIVO,
            }
        ],
    )
    assert parto.nascimentos.get().animal.pai is None


def test_cancelamento_de_parto_bloqueia_dependentes(vaca: Animal) -> None:
    parto = registrar_parto(
        vaca=vaca,
        data_hora=timezone.now() - timedelta(days=1),
        resultado=Parto.Resultado.NORMAL,
        bezerros=[
            {
                "identificacao": "CANCEL-BEZ",
                "sexo": Animal.Sexo.FEMEA,
                "situacao": Nascimento.Situacao.VIVO,
            }
        ],
    )
    with pytest.raises(ValidationError, match="nascimentos vinculados"):
        cancelar_parto(parto=parto, justificativa="Lançamento duplicado")
    parto.refresh_from_db()
    assert parto.situacao == Parto.Situacao.REGISTRADO


def test_correcao_do_parto_atualiza_nascimento_e_entrada(vaca: Animal) -> None:
    parto = registrar_parto(
        vaca=vaca,
        data_hora=timezone.now() - timedelta(days=2),
        resultado=Parto.Resultado.NORMAL,
        bezerros=[
            {
                "identificacao": "CORR-BEZ",
                "sexo": Animal.Sexo.MACHO,
                "situacao": Nascimento.Situacao.VIVO,
            }
        ],
    )
    nova_data_hora = parto.data_hora + timedelta(days=1)
    corrigir_parto(
        parto=parto,
        justificativa="Data conferida no caderno",
        data_hora=nova_data_hora,
    )
    cria = parto.nascimentos.get().animal
    cria.refresh_from_db()
    nova_data = timezone.localtime(nova_data_hora).date()
    assert cria.data_nascimento == nova_data
    assert cria.data_entrada == nova_data


def test_impede_segundo_parto_na_mesma_cobertura(vaca: Animal) -> None:
    cobertura = criar_cobertura(vaca, data_cobertura=timezone.localdate() - timedelta(days=283))
    dados = {
        "vaca": vaca,
        "cobertura": cobertura,
        "data_hora": timezone.now() - timedelta(minutes=1),
        "resultado": Parto.Resultado.NORMAL,
        "bezerros": [
            {
                "identificacao": "UNICO-1",
                "sexo": Animal.Sexo.FEMEA,
                "situacao": Nascimento.Situacao.VIVO,
            }
        ],
    }
    registrar_parto(**dados)
    dados["bezerros"] = [
        {
            "identificacao": "UNICO-2",
            "sexo": Animal.Sexo.MACHO,
            "situacao": Nascimento.Situacao.VIVO,
        }
    ]
    with pytest.raises(ValidationError, match="já possui"):
        registrar_parto(**dados)


def test_rejeita_datas_futuras(vaca: Animal) -> None:
    with pytest.raises(ValidationError, match="futura"):
        criar_cobertura(vaca, data_cobertura=timezone.localdate() + timedelta(days=1))


def test_lista_de_coberturas_tem_resposta_parcial_htmx(
    client, django_user_model, vaca: Animal
) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="repro", password="teste")
    client.force_login(usuario)
    criar_cobertura(vaca)
    resposta = client.get(
        reverse("reproducao:coberturas"),
        {"q": "V-REPRO"},
        HTTP_HX_REQUEST="true",
    )
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "V-REPRO" in conteudo
    assert "<!doctype html>" not in conteudo.lower()


def test_lista_coberturas_por_boi_mostra_vaca_data_e_foto(
    client, django_user_model, vaca: Animal, touro: Animal
) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="coberturas-boi", password="teste")
    client.force_login(usuario)
    vaca.nome = "Mimosa"
    vaca.save(update_fields=["nome"])
    touro.nome = "Trovão"
    touro.save(update_fields=["nome"])
    Animal.objects.filter(pk=touro.pk).update(foto="animais/trovao/foto.jpg")
    cobertura = criar_cobertura(vaca, touro)

    resposta = client.get(reverse("reproducao:coberturas_por_touro"), {"q": "Trovão"})
    conteudo = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Coberturas por boi" in conteudo
    assert "Trovão" in conteudo
    assert "Mimosa" in conteudo
    assert cobertura.data.strftime("%d/%m/%Y") in conteudo
    assert "animais/trovao/foto.jpg" in conteudo
