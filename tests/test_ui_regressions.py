from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.financeiro.models import FechamentoLeite, Laticinio, RecebimentoLeite
from apps.lactacao.models import Lactacao
from apps.leite.forms import ProducaoAnimalForm
from apps.leite.models import Ordenha
from apps.leite.services import registrar_producao, salvar_ordenha
from apps.rebanho.models import Animal
from apps.reproducao.forms import BezerroFormSet
from apps.reproducao.models import Cobertura, Parto
from apps.reproducao.services import registrar_cobertura

pytestmark = pytest.mark.django_db


def autenticar(client, django_user_model, *, username: str) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username=username, password="senha-forte-123")
    client.force_login(usuario)


def criar_animal(*, identificacao: str, sexo: str = Animal.Sexo.FEMEA) -> Animal:
    return Animal.objects.create(
        identificacao=identificacao,
        sexo=sexo,
        tipo_animal=(
            Animal.TipoAnimal.VACA
            if sexo == Animal.Sexo.FEMEA
            else Animal.TipoAnimal.BOI
        ),
        data_nascimento=timezone.localdate() - timedelta(days=365 * 3),
        situacao=Animal.Situacao.ATIVO,
    )


def test_navegacao_e_retornos_continuam_utilizaveis_sem_javascript(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    autenticar(client, django_user_model, username="navegacao-ui")

    resposta = client.get(reverse("core:dashboard"))
    conteudo = resposta.content.decode()

    assert resposta.status_code == 200
    assert '<details class="user-menu">' in conteudo
    assert "x-data=" not in conteudo
    for destino in (
        reverse("rebanho:animais"),
        reverse("reproducao:coberturas"),
        reverse("leite:ordenha_nova"),
        reverse("relatorios:index"),
    ):
        assert f'href="{destino}"' in conteudo
    for destino_removido in (
        reverse("lactacao:lista"),
        reverse("saude:inicio"),
        reverse("financeiro:inicio"),
        reverse("core:alertas"),
        reverse("core:configuracoes"),
    ):
        assert f'href="{destino_removido}"' not in conteudo
    assert '<details class="mobile-more">' in conteudo

    formulario = client.get(reverse("rebanho:animal_novo"))
    assert "javascript:" not in formulario.content.decode()


def test_formulario_de_parto_oferece_fallback_para_gemeos_e_cadastra_duas_crias(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    autenticar(client, django_user_model, username="parto-ui")
    vaca = criar_animal(identificacao="V-PARTO-UI")
    touro = criar_animal(identificacao="T-PARTO-UI", sexo=Animal.Sexo.MACHO)
    cobertura = registrar_cobertura(
        vaca=vaca,
        touro=touro,
        data_cobertura=timezone.localdate() - timedelta(days=283),
        tipo=Cobertura.Tipo.MONTA_NATURAL,
        forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
    )
    url = reverse("reproducao:cobertura_parto", kwargs={"cobertura_id": cobertura.pk})

    pagina = client.get(url)
    formset = pagina.context["formset"]
    conteudo = pagina.content.decode()
    assert pagina.status_code == 200
    assert formset.total_form_count() == 1
    assert formset.max_num == 5
    assert 'id="adicionar-bezerro"' in conteudo
    assert "bezerros-__prefix__-nome" in conteudo
    assert "Iniciar lactação" not in conteudo

    resposta = client.post(
        url,
        {
            "vaca": str(vaca.pk),
            "cobertura": str(cobertura.pk),
            "data_hora": (timezone.localtime() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"),
            "resultado": Parto.Resultado.NORMAL,
            "responsavel": "Operador",
            "observacoes": "Parto gemelar registrado pela interface.",
            "bezerros-TOTAL_FORMS": "2",
            "bezerros-INITIAL_FORMS": "0",
            "bezerros-MIN_NUM_FORMS": "0",
            "bezerros-MAX_NUM_FORMS": "5",
            "bezerros-0-nome": "Lua",
            "bezerros-0-sexo": Animal.Sexo.FEMEA,
            "bezerros-1-nome": "Sol",
            "bezerros-1-sexo": Animal.Sexo.MACHO,
        },
    )

    assert resposta.status_code == 302
    parto = Parto.objects.get(cobertura=cobertura)
    assert resposta.url == reverse(
        "reproducao:parto_detalhe",
        kwargs={"parto_id": parto.pk},
    )
    assert parto.quantidade_bezerros == 2
    assert Animal.objects.filter(mae=vaca, pai=touro, nascimento__parto=parto).count() == 2
    detalhe_parto = client.get(
        reverse("reproducao:parto_detalhe", kwargs={"parto_id": parto.pk})
    )
    assert reverse("lactacao:nova_do_parto", kwargs={"parto_id": parto.pk}) not in (
        detalhe_parto.content.decode()
    )


def test_segunda_ficha_vazia_do_parto_sem_javascript_e_ignorada() -> None:
    formset = BezerroFormSet(
        data={
            "bezerros-TOTAL_FORMS": "2",
            "bezerros-INITIAL_FORMS": "0",
            "bezerros-MIN_NUM_FORMS": "0",
            "bezerros-MAX_NUM_FORMS": "5",
            "bezerros-0-nome": "Cria única",
            "bezerros-0-sexo": Animal.Sexo.FEMEA,
            "bezerros-1-nome": "",
            "bezerros-1-cor": "",
            "bezerros-1-sexo": "",
        },
        prefix="bezerros",
    )

    assert formset.is_valid(), formset.errors


def test_foto_do_animal_usa_rota_privada_autenticada(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    autenticar(client, django_user_model, username="foto-ui")
    animal = criar_animal(identificacao="FOTO-UI")
    animal.foto.name = "animais/foto-ui/retrato.jpg"
    animal.save(update_fields=["foto"])

    resposta = client.get(reverse("rebanho:animal_detalhe", kwargs={"animal_id": animal.pk}))
    url_privada = reverse("core:arquivo_privado", kwargs={"caminho": animal.foto.name})

    assert resposta.status_code == 200
    assert f'src="{url_privada}"' in resposta.content.decode()
    assert "/media/" not in resposta.content.decode()


def test_listas_htmx_nao_interceptam_links_para_paginas_completas(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    autenticar(client, django_user_model, username="htmx-ui")

    for nome_rota in ("leite:ordenhas", "financeiro:entregas"):
        resposta = client.get(reverse(nome_rota), HTTP_HX_REQUEST="true")
        conteudo = resposta.content.decode()
        assert resposta.status_code == 200
        assert 'id="lista-registros"' in conteudo
        assert "hx-boost" not in conteudo


def test_conciliacao_individual_registra_automaticamente_e_filtra_vacas(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    autenticar(client, django_user_model, username="conciliacao-ui")
    vaca_ativa = criar_animal(identificacao="V-ATIVA-UI")
    vaca_seca = criar_animal(identificacao="V-SECA-UI")
    Lactacao.objects.create(
        vaca=vaca_ativa,
        ordem=1,
        data_inicio=timezone.localdate() - timedelta(days=30),
        situacao=Lactacao.Situacao.ATIVA,
    )
    Lactacao.objects.create(
        vaca=vaca_seca,
        ordem=1,
        data_inicio=timezone.localdate() - timedelta(days=60),
        data_secagem=timezone.localdate() - timedelta(days=2),
        situacao=Lactacao.Situacao.SECA,
    )
    escolhas = set(ProducaoAnimalForm().fields["vaca"].queryset.values_list("pk", flat=True))
    assert vaca_ativa.pk in escolhas
    assert vaca_seca.pk not in escolhas

    ordenha = salvar_ordenha(
        data=timezone.localdate(),
        periodo=Ordenha.Periodo.MANHA,
        modo=Ordenha.Modo.INDIVIDUAL,
        quantidade_total=Decimal("10.000"),
        quantidade_vacas=0,
        responsavel="Operador",
    )
    registrar_producao(
        ordenha=ordenha,
        vaca=vaca_ativa,
        quantidade_litros=Decimal("8.500"),
    )
    url = reverse("leite:ordenha_conciliar", kwargs={"pk": ordenha.pk})

    conciliada = client.post(url)
    assert conciliada.status_code == 302
    assert conciliada.url == reverse("leite:ordenha_detalhe", kwargs={"pk": ordenha.pk})
    ordenha.refresh_from_db()
    assert ordenha.justificativa_divergencia == (
        "Alteração registrada automaticamente pelo sistema."
    )


def test_lista_de_recebimentos_expoe_download_do_anexo(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    autenticar(client, django_user_model, username="recebimento-ui")
    hoje = timezone.localdate()
    laticinio = Laticinio.objects.create(razao_social="Comprador UI", ativo=True)
    fechamento = FechamentoLeite.objects.create(
        laticinio=laticinio,
        competencia=hoje.replace(day=1),
        data_inicial=hoje.replace(day=1),
        data_final=hoje,
    )
    recebimento = RecebimentoLeite.objects.create(
        fechamento=fechamento,
        data=hoje,
        valor=Decimal("25.00"),
        forma_pagamento=RecebimentoLeite.FormaPagamento.PIX,
        anexo="financeiro/recebimentos/comprovante-ui.pdf",
    )

    resposta = client.get(reverse("financeiro:recebimentos"))
    url_anexo = reverse("financeiro:arquivo_privado", args=("recebimento", recebimento.pk))

    assert resposta.status_code == 200
    assert "Baixar anexo" in resposta.content.decode()
    assert f'href="{url_anexo}"' in resposta.content.decode()
