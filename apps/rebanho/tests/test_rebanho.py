from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ArquivoAnexo
from apps.rebanho.forms import AnimalForm, CadastroBezerroForm, CadastroNovilhaForm
from apps.rebanho.models import Animal, Lote
from apps.rebanho.selectors import linha_do_tempo
from apps.rebanho.services import (
    excluir_animal,
    inativar_animal,
    movimentar_animal,
    registrar_pesagem,
    salvar_animal,
)
from apps.reproducao.models import Cobertura
from apps.reproducao.services import registrar_cobertura

pytestmark = pytest.mark.django_db


def animal(**alteracoes):  # type: ignore[no-untyped-def]
    dados = {
        "identificacao": f"A-{Animal.objects.count() + 1}",
        "sexo": Animal.Sexo.FEMEA,
        "data_nascimento": timezone.localdate() - timedelta(days=365 * 3),
        "situacao": Animal.Situacao.ATIVO,
    }
    dados.update(alteracoes)
    return salvar_animal(**dados)


def test_identificacao_e_unica_e_normalizada() -> None:
    primeiro = animal(identificacao=" brinco-10 ")
    assert primeiro.identificacao == "BRINCO-10"
    with pytest.raises(ValidationError):
        animal(identificacao="brinco-10")


def test_identificacao_nao_colide_entre_definitiva_e_provisoria() -> None:
    animal(identificacao="CRUZADA-1")
    with pytest.raises(ValidationError, match="definitiva ou provisória"):
        animal(identificacao=None, identificacao_provisoria="cruzada-1")


def test_identificacao_e_opcional_quando_animal_tem_nome() -> None:
    sem_identificacao = animal(
        identificacao=None,
        identificacao_provisoria=None,
        nome="Estrela",
    )
    assert sem_identificacao.identificador_exibicao == "Estrela"
    provisoria = animal(identificacao=None, identificacao_provisoria="temp-1")
    assert provisoria.identificador_exibicao == "TEMP-1"


def test_valida_sexo_da_mae_e_do_pai() -> None:
    macho = animal(identificacao="M-1", sexo=Animal.Sexo.MACHO)
    femea = animal(identificacao="F-1", sexo=Animal.Sexo.FEMEA)
    com_mae_invalida = Animal(
        identificacao="B-1",
        sexo=Animal.Sexo.FEMEA,
        data_nascimento=timezone.localdate(),
        mae=macho,
    )
    with pytest.raises(ValidationError) as erro_mae:
        com_mae_invalida.full_clean()
    assert "mae" in erro_mae.value.message_dict

    com_pai_invalido = Animal(
        identificacao="B-2",
        sexo=Animal.Sexo.MACHO,
        data_nascimento=timezone.localdate(),
        pai=femea,
    )
    with pytest.raises(ValidationError) as erro_pai:
        com_pai_invalido.full_clean()
    assert "pai" in erro_pai.value.message_dict


def test_impede_autorreferencia_e_ciclo_de_parentesco() -> None:
    vaca = animal(identificacao="V-1")
    vaca.mae = vaca
    with pytest.raises(ValidationError, match="si mesmo"):
        vaca.full_clean()

    filha = animal(identificacao="F-2", mae=vaca)
    with pytest.raises(ValidationError, match="ciclo"):
        salvar_animal(
            animal=vaca,
            mae=filha,
            justificativa_parentesco="Correção conferida",
        )


def test_mudanca_de_parentesco_exige_motivo_e_preserva_historico() -> None:
    mae_um = animal(identificacao="MAE-1")
    mae_dois = animal(identificacao="MAE-2")
    filha = animal(identificacao="FILHA-1", mae=mae_um)
    with pytest.raises(ValidationError, match="Justifique"):
        salvar_animal(animal=filha, mae=mae_dois)
    atualizada = salvar_animal(
        animal=filha,
        mae=mae_dois,
        justificativa_parentesco="Exame de filiação conferido",
    )
    historico = atualizada.historico_parentesco.get()
    assert historico.mae_anterior == mae_um
    assert historico.mae_nova == mae_dois
    assert historico.justificativa == "Exame de filiação conferido"


def test_idade_e_categoria_sao_calculadas_sem_armazenar_idade() -> None:
    hoje = timezone.localdate()
    nascimento = date(hoje.year - 2, hoje.month, min(hoje.day, 28))
    novilha = animal(identificacao="NOV-1", data_nascimento=nascimento)
    assert 23 <= novilha.idade_em_meses <= 24
    assert novilha.idade_em_anos in {1, 2}
    assert novilha.categoria == "Novilha"


def test_movimentacao_atualiza_lote_e_preserva_anterior() -> None:
    lote_um = Lote.objects.create(nome="Maternidade")
    lote_dois = Lote.objects.create(nome="Produção")
    vaca = animal(identificacao="LOT-1", lote=lote_um)
    movimento = movimentar_animal(
        animal=vaca,
        novo_lote=lote_dois,
        data_movimentacao=timezone.localdate(),
        motivo="Mudança de manejo",
    )
    vaca.refresh_from_db()
    assert movimento.lote_anterior == lote_um
    assert movimento.novo_lote == lote_dois
    assert vaca.lote == lote_dois


def test_linha_do_tempo_usa_data_efetiva_do_evento() -> None:
    lote = Lote.objects.create(nome="Retroativo")
    vaca = animal(identificacao="TEMPO-1")
    data_movimento = timezone.localdate() - timedelta(days=5)
    movimentar_animal(
        animal=vaca,
        novo_lote=lote,
        data_movimentacao=data_movimento,
        motivo="Registro retroativo conferido",
    )
    evento = linha_do_tempo(animal=vaca, tipo="lote")[0]
    assert timezone.localtime(evento["data"]).date() == data_movimento


def test_cadastro_inicial_cria_historicos_de_lote_e_peso() -> None:
    lote = Lote.objects.create(nome="Inicial")
    vaca = animal(identificacao="INI-1", lote=lote, peso_atual=Decimal("350.00"))
    movimento = vaca.movimentacoes_lote.get()
    pesagem = vaca.pesagens.get()
    assert movimento.lote_anterior is None
    assert movimento.novo_lote == lote
    assert pesagem.peso_kg == Decimal("350.00")


def test_upload_de_foto_registra_metadados_e_preserva_substituicao() -> None:
    primeira_foto = SimpleUploadedFile(
        "Estrela.PNG",
        b"\x89PNG\r\n\x1a\n" + b"foto",
        content_type="image/png",
    )
    vaca = animal(identificacao="FOTO-META", foto=primeira_foto)
    primeiro = ArquivoAnexo.objects.get(object_id=str(vaca.pk), campo="foto")
    assert primeiro.nome_original == "Estrela.PNG"
    assert primeiro.mime_type == "image/png"
    assert primeiro.tamanho_bytes == len(primeira_foto)
    assert primeiro.caminho == vaca.foto.name

    segunda_foto = SimpleUploadedFile(
        "estrela-nova.jpg",
        b"\xff\xd8\xff" + b"foto",
        content_type="image/jpeg",
    )
    salvar_animal(animal=vaca, foto=segunda_foto)
    primeiro.refresh_from_db()
    atual = ArquivoAnexo.objects.get(object_id=str(vaca.pk), campo="foto", ativo=True)
    assert not primeiro.ativo
    assert primeiro.substituido_em is not None
    assert atual.nome_original == "estrela-nova.jpg"


def test_edicao_permite_remover_foto_atual(
    client, django_user_model, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="remover-foto", password="teste")
    client.force_login(usuario)
    foto = SimpleUploadedFile(
        "mimosa.png",
        b"\x89PNG\r\n\x1a\n" + b"foto",
        content_type="image/png",
    )
    vaca = animal(identificacao=None, nome="Mimosa", foto=foto)
    caminho_foto = vaca.foto.name
    armazenamento = vaca.foto.storage
    assert armazenamento.exists(caminho_foto)
    url = reverse("rebanho:animal_editar", kwargs={"animal_id": vaca.pk})

    pagina = client.get(url)
    conteudo = pagina.content.decode()
    assert pagina.status_code == 200
    assert "Foto atual" in conteudo
    assert "Remover foto atual" in conteudo
    assert 'name="remover_foto"' in conteudo

    with django_capture_on_commit_callbacks(execute=True):
        resposta = client.post(
            url,
            {
                "nome": "Mimosa",
                "cor": "",
                "sexo": Animal.Sexo.FEMEA,
                "remover_foto": "on",
            },
        )

    assert resposta.status_code == 302, resposta.context["form"].errors.as_json()
    vaca.refresh_from_db()
    assert not vaca.foto
    assert not armazenamento.exists(caminho_foto)
    assert not ArquivoAnexo.objects.filter(
        object_id=str(vaca.pk),
        campo="foto",
        caminho=caminho_foto,
        ativo=True,
    ).exists()


def test_edicao_direta_nao_reescreve_lote_ou_peso() -> None:
    lote_um = Lote.objects.create(nome="Um")
    lote_dois = Lote.objects.create(nome="Dois")
    vaca = animal(identificacao="HIST-1", lote=lote_um, peso_atual=Decimal("300.00"))
    with pytest.raises(ValidationError, match="Mudar lote"):
        salvar_animal(animal=vaca, lote=lote_dois)
    with pytest.raises(ValidationError, match="Registrar pesagem"):
        salvar_animal(animal=vaca, peso_atual=Decimal("301.00"))


def test_correcao_de_sexo_nao_invalida_papel_parental() -> None:
    mae = animal(identificacao="MAE-HIST")
    animal(identificacao="FILHO-HIST", mae=mae)
    with pytest.raises(ValidationError, match="histórico como fêmea"):
        salvar_animal(
            animal=mae,
            sexo=Animal.Sexo.MACHO,
            justificativa_correcao="Ficha antiga estava incorreta",
        )


def test_correcao_de_nascimento_nao_ultrapassa_evento() -> None:
    vaca = animal(identificacao="DATA-HIST")
    data_evento = timezone.localdate() - timedelta(days=10)
    registrar_pesagem(animal=vaca, data_pesagem=data_evento, peso_kg=Decimal("380.00"))
    with pytest.raises(ValidationError, match="evento já registrado"):
        salvar_animal(
            animal=vaca,
            data_nascimento=data_evento + timedelta(days=1),
            justificativa_correcao="Conferência documental",
        )


def test_inativacao_bloqueia_cobertura_aberta() -> None:
    vaca = animal(identificacao="SAIDA-PRENHE")
    registrar_cobertura(
        vaca=vaca,
        data_cobertura=timezone.localdate() - timedelta(days=30),
        tipo=Cobertura.Tipo.MONTA_NATURAL,
        forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
    )
    with pytest.raises(ValidationError, match="cobertura aberta"):
        inativar_animal(
            animal=vaca,
            situacao=Animal.Situacao.VENDIDO,
            motivo="Venda",
        )


def test_pesagem_atualiza_peso_e_calcula_evolucao() -> None:
    vaca = animal(identificacao="PES-1")
    primeira = registrar_pesagem(
        animal=vaca,
        data_pesagem=timezone.localdate() - timedelta(days=10),
        peso_kg=Decimal("400.00"),
    )
    segunda = registrar_pesagem(
        animal=vaca,
        data_pesagem=timezone.localdate(),
        peso_kg=Decimal("410.00"),
    )
    vaca.refresh_from_db()
    assert vaca.peso_atual == Decimal("410.00")
    assert segunda.diferenca_anterior == Decimal("10.00")
    assert segunda.ganho_medio_diario == Decimal("1.00")
    assert primeira.diferenca_anterior is None


def test_rotas_exigem_login(client) -> None:  # type: ignore[no-untyped-def]
    resposta = client.get(reverse("rebanho:animais"))
    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


def test_formulario_de_animal_tem_somente_os_quatro_campos_solicitados() -> None:
    formulario = AnimalForm()

    assert list(formulario.fields) == ["nome", "cor", "foto", "sexo"]
    assert formulario.fields["nome"].required is True
    assert all(formulario.fields[campo].required is False for campo in ("cor", "foto", "sexo"))
    assert formulario["sexo"].value() == Animal.Sexo.FEMEA


def test_formulario_de_bezerro_acrescenta_somente_a_mae_opcional() -> None:
    formulario = CadastroBezerroForm()

    assert list(formulario.fields) == ["nome", "cor", "foto", "sexo", "mae"]
    assert formulario.fields["mae"].required is False


def test_cadastro_minimo_exige_apenas_nome(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="cadastro-minimo", password="teste")
    client.force_login(usuario)

    resposta = client.post(reverse("rebanho:animal_novo"), {"nome": "Estrela"})

    assert resposta.status_code == 302
    cadastrado = Animal.objects.get(nome="Estrela")
    assert resposta.url == reverse("rebanho:animal_novo")
    assert cadastrado.cor == ""
    assert cadastrado.sexo == ""
    assert not cadastrado.foto
    assert cadastrado.data_nascimento is None


def test_cadastro_rapido_de_bezerro_define_nascimento_como_hoje(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="cadastro-bezerro", password="teste")
    client.force_login(usuario)
    mae = animal(nome="Mimosa")

    resposta = client.post(
        reverse("rebanho:bezerro_novo"),
        {
            "nome": "Pingo",
            "cor": "Malhado",
            "sexo": "",
            "mae": str(mae.pk),
        },
    )

    assert resposta.status_code == 302
    bezerro = Animal.objects.get(nome="Pingo")
    assert resposta.url == reverse("rebanho:bezerro_novo")
    assert bezerro.data_nascimento == timezone.localdate()
    assert bezerro.data_entrada == timezone.localdate()
    assert bezerro.mae == mae
    assert bezerro.categoria == "Bezerro"


def test_cadastro_de_novilha_define_femea_e_permanece_no_formulario(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="cadastro-novilha", password="teste")
    client.force_login(usuario)
    nascimento = timezone.localdate() - timedelta(days=365 * 2)

    resposta = client.post(
        reverse("rebanho:novilha_nova"),
        {
            "nome": "Jade",
            "cor": "Parda",
            "sexo": Animal.Sexo.MACHO,
            "data_nascimento": nascimento.strftime("%d/%m/%Y"),
        },
    )

    novilha = Animal.objects.get(nome="Jade")
    assert resposta.status_code == 302
    assert resposta.url == reverse("rebanho:novilha_nova")
    assert novilha.sexo == Animal.Sexo.FEMEA
    assert novilha.data_nascimento == nascimento
    assert novilha.categoria == "Novilha"


def test_formulario_de_novilha_rejeita_idade_de_bezerra() -> None:
    formulario = CadastroNovilhaForm(
        data={
            "nome": "Muito nova",
            "cor": "",
            "sexo": Animal.Sexo.FEMEA,
            "data_nascimento": timezone.localdate().strftime("%d/%m/%Y"),
        }
    )

    assert not formulario.is_valid()
    assert "data_nascimento" in formulario.errors


def test_lista_autenticada_renderiza_e_htmx_retorna_somente_cartoes(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="produtor", password="teste")
    client.force_login(usuario)
    encontrado = animal(identificacao="BUSCA-HTMX")
    registrar_pesagem(
        animal=encontrado,
        data_pesagem=timezone.localdate(),
        peso_kg=Decimal("420.00"),
    )

    pagina = client.get(reverse("rebanho:animais"))
    assert pagina.status_code == 200
    assert 'hx-target="#animal-results"' in pagina.content.decode()

    parcial = client.get(
        reverse("rebanho:animais"),
        {"q": "BUSCA-HTMX"},
        HTTP_HX_REQUEST="true",
    )
    conteudo = parcial.content.decode()
    assert parcial.status_code == 200
    assert "BUSCA-HTMX" in conteudo
    assert "<!doctype html>" not in conteudo.lower()

    detalhe = client.get(
        reverse("rebanho:animal_detalhe", kwargs={"animal_id": encontrado.pk}),
        {"tipo": "cadastro"},
    )
    assert detalhe.status_code == 200
    assert "Dados" in detalhe.content.decode()
    assert "Coberturas" in detalhe.content.decode()
    assert "dados-grafico-peso" not in detalhe.content.decode()


def test_lista_do_rebanho_exibe_animais_em_tabela_com_foto(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="lista-gado", password="teste")
    client.force_login(usuario)
    mimosa = animal(
        identificacao=None,
        identificacao_provisoria=None,
        nome="Mimosa",
        cor="Malhada",
    )
    Animal.objects.filter(pk=mimosa.pk).update(foto="animais/mimosa/foto.jpg")
    boi = animal(identificacao=None, nome="Trovão", sexo=Animal.Sexo.MACHO)
    data_cobertura = timezone.localdate() - timedelta(days=12)
    registrar_cobertura(
        vaca=mimosa,
        touro=boi,
        data_cobertura=data_cobertura,
        tipo=Cobertura.Tipo.MONTA_NATURAL,
        forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
    )

    resposta = client.get(reverse("rebanho:animais"))
    conteudo = resposta.content.decode()

    assert resposta.status_code == 200
    assert 'aria-label="Lista do rebanho"' in conteudo
    assert "<table" in conteudo
    assert "Mimosa" in conteudo
    assert "Data de cobertura" in conteudo
    assert data_cobertura.strftime("%d/%m/%Y") in conteudo
    assert "<th>Cor</th>" not in conteudo
    assert "<th>Mãe</th>" in conteudo
    assert "<th>Ações</th>" in conteudo
    assert 'class="animal-avatar"' in conteudo
    assert "animais/mimosa/foto.jpg" in conteudo


def test_excluir_vaca_mantem_bezerro_sem_mae(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    usuario = django_user_model.objects.create_user(username="excluir-vaca", password="teste")
    client.force_login(usuario)
    mae = animal(identificacao=None, nome="Mimosa")
    bezerro = animal(
        identificacao=None,
        nome="Pingo",
        data_nascimento=timezone.localdate(),
        mae=mae,
    )
    url = reverse("rebanho:animal_excluir", kwargs={"animal_id": mae.pk})

    confirmacao = client.get(url)
    assert confirmacao.status_code == 200
    assert "continuará cadastrado, mas sem mãe vinculada" in confirmacao.content.decode()

    resposta = client.post(url)

    assert resposta.status_code == 302
    assert not Animal.objects.filter(pk=mae.pk).exists()
    bezerro.refresh_from_db()
    assert bezerro.mae is None


def test_excluir_boi_preserva_cobertura_sem_boi() -> None:
    vaca = animal(identificacao="VACA-EXCLUSAO")
    boi = animal(identificacao="BOI-EXCLUSAO", sexo=Animal.Sexo.MACHO)
    cobertura = registrar_cobertura(
        vaca=vaca,
        touro=boi,
        data_cobertura=timezone.localdate() - timedelta(days=10),
        tipo=Cobertura.Tipo.MONTA_NATURAL,
        forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
    )

    excluir_animal(animal=boi)

    cobertura.refresh_from_db()
    assert cobertura.touro is None


def test_excluir_vaca_remove_suas_coberturas() -> None:
    vaca = animal(identificacao="VACA-COBERTURA-EXCLUSAO")
    boi = animal(identificacao="BOI-COBERTURA-EXCLUSAO", sexo=Animal.Sexo.MACHO)
    cobertura = registrar_cobertura(
        vaca=vaca,
        touro=boi,
        data_cobertura=timezone.localdate() - timedelta(days=10),
        tipo=Cobertura.Tipo.MONTA_NATURAL,
        forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
    )

    excluir_animal(animal=vaca)

    assert not Animal.objects.filter(pk=vaca.pk).exists()
    assert not Cobertura.objects.filter(pk=cobertura.pk).exists()
    assert Animal.objects.filter(pk=boi.pk).exists()
