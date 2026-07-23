from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.alertas import (
    verificar_backup,
    verificar_conciliacoes,
    verificar_espaco_disco,
    verificar_financeiro,
    verificar_rotina_leite,
)
from apps.core.backup_status import ler_backup_status, registrar_backup_sucesso
from apps.core.models import Alerta, ConfiguracaoSistema
from apps.financeiro.models import EntregaLeite, FechamentoLeite, Laticinio
from apps.lactacao.models import Lactacao
from apps.leite.models import Ordenha
from apps.rebanho.models import Animal
from apps.reproducao.models import Cobertura

AGORA = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)


def test_comando_registra_marcador_atomico_sem_expor_caminho(settings, tmp_path):
    settings.BACKUP_STATUS_FILE = tmp_path / ".sistema" / "ultimo_backup.json"
    saida = StringIO()

    call_command(
        "registrar_backup_sucesso",
        arquivo="/mnt/seguro/gestao-rural-20260722T160000Z.tar.gz",
        stdout=saida,
    )

    status = ler_backup_status()
    assert status is not None
    assert status.arquivo == "gestao-rural-20260722T160000Z.tar.gz"
    assert "/mnt/seguro" not in settings.BACKUP_STATUS_FILE.read_text(encoding="utf-8")
    assert "Backup registrado" in saida.getvalue()


@pytest.mark.django_db(transaction=True)
def test_exporta_copia_sqlite_consistente(tmp_path) -> None:
    ConfiguracaoSistema.obter()
    destino = tmp_path / "database.sqlite3"

    call_command("exportar_backup_sqlite", saida=str(destino), stdout=StringIO())

    assert destino.is_file()
    with sqlite3.connect(destino) as banco:
        assert banco.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert banco.execute("SELECT COUNT(*) FROM core_configuracaosistema").fetchone() == (1,)


@pytest.mark.django_db
def test_alerta_de_backup_ausente_nao_duplica_e_fecha_apos_sucesso(settings, tmp_path):
    settings.BACKUP_MONITOR_ENABLED = True
    settings.BACKUP_MAX_AGE_HOURS = 36
    settings.BACKUP_STATUS_FILE = tmp_path / "ultimo_backup.json"

    assert verificar_backup(agora=AGORA) == 1
    primeiro = Alerta.objects.get(chave="operacional:backup")
    assert primeiro.titulo == "Nenhum backup confirmado"
    assert primeiro.resolvido is False

    assert verificar_backup(agora=AGORA) == 1
    assert Alerta.objects.filter(chave="operacional:backup", resolvido=False).count() == 1
    assert Alerta.objects.get(chave="operacional:backup").pk == primeiro.pk

    registrar_backup_sucesso(
        "gestao-rural-20260722T150000Z.tar.gz",
        concluido_em=AGORA - timedelta(hours=1),
    )
    assert verificar_backup(agora=AGORA) == 0

    primeiro.refresh_from_db()
    assert primeiro.resolvido is True
    assert primeiro.resolvido_em is not None


@pytest.mark.django_db
def test_alerta_indica_backup_com_idade_acima_do_limite(settings, tmp_path):
    settings.BACKUP_MONITOR_ENABLED = True
    settings.BACKUP_MAX_AGE_HOURS = 36
    settings.BACKUP_STATUS_FILE = tmp_path / "ultimo_backup.json"
    registrar_backup_sucesso(
        "gestao-rural-antigo.tar.gz",
        concluido_em=AGORA - timedelta(hours=37),
    )

    assert verificar_backup(agora=AGORA) == 1

    alerta = Alerta.objects.get(chave="operacional:backup")
    assert alerta.titulo == "Backup atrasado"
    assert "gestao-rural-antigo.tar.gz" in alerta.mensagem
    assert "36 hora(s)" in alerta.mensagem


@pytest.mark.django_db
def test_alerta_de_disco_nao_duplica_e_fecha_quando_espaco_normaliza(
    settings,
    tmp_path,
    monkeypatch,
):
    settings.DISK_MONITOR_ENABLED = True
    settings.DISK_MONITOR_PATH = tmp_path
    settings.DISK_MIN_FREE_PERCENT = 10
    pouco_espaco = SimpleNamespace(total=1000, used=950, free=50)
    monkeypatch.setattr("apps.core.alertas.shutil.disk_usage", lambda _path: pouco_espaco)

    assert verificar_espaco_disco() == 1
    primeiro = Alerta.objects.get(chave="operacional:espaco-disco")
    assert primeiro.titulo == "Pouco espaço livre em disco"
    assert "5.0% livre" in primeiro.mensagem

    assert verificar_espaco_disco() == 1
    assert Alerta.objects.filter(chave="operacional:espaco-disco", resolvido=False).count() == 1
    assert Alerta.objects.get(chave="operacional:espaco-disco").pk == primeiro.pk

    espaco_normal = SimpleNamespace(total=1000, used=500, free=500)
    monkeypatch.setattr("apps.core.alertas.shutil.disk_usage", lambda _path: espaco_normal)
    assert verificar_espaco_disco() == 0

    primeiro.refresh_from_db()
    assert primeiro.resolvido is True
    assert primeiro.resolvido_em is not None


@pytest.mark.django_db
def test_comando_periodico_existente_executa_monitores_operacionais(
    settings,
    tmp_path,
    monkeypatch,
):
    settings.BACKUP_MONITOR_ENABLED = True
    settings.BACKUP_STATUS_FILE = tmp_path / "marcador-ausente.json"
    settings.DISK_MONITOR_ENABLED = True
    settings.DISK_MONITOR_PATH = tmp_path
    settings.DISK_MIN_FREE_PERCENT = 10
    pouco_espaco = SimpleNamespace(total=1000, used=950, free=50)
    monkeypatch.setattr("apps.core.alertas.shutil.disk_usage", lambda _path: pouco_espaco)
    saida = StringIO()

    call_command("verificar_alertas", stdout=saida)

    assert Alerta.objects.filter(tipo="backup", resolvido=False).count() == 1
    assert Alerta.objects.filter(tipo="espaco_disco", resolvido=False).count() == 1
    assert "backup: 1" in saida.getvalue()
    assert "espaco_disco: 1" in saida.getvalue()


@pytest.mark.django_db
def test_rotina_leite_alerta_falta_de_ordenha_e_secagem_proxima() -> None:
    hoje = timezone.localdate()
    vaca = Animal.objects.create(
        identificacao="ROT-001",
        sexo=Animal.Sexo.FEMEA,
        data_nascimento=hoje - timedelta(days=1000),
    )
    Lactacao.objects.create(
        vaca=vaca,
        ordem=1,
        data_inicio=hoje - timedelta(days=30),
        situacao=Lactacao.Situacao.ATIVA,
    )
    Cobertura.objects.create(
        vaca=vaca,
        data=hoje - timedelta(days=220),
        tipo=Cobertura.Tipo.MONTA_NATURAL,
        situacao=Cobertura.Situacao.PRENHEZ_CONFIRMADA,
        previsao_atual_parto=hoje + timedelta(days=63),
    )

    assert verificar_rotina_leite() == 2
    assert Alerta.objects.filter(
        tipo="rotina_leite",
        titulo="Vaca sem ordenha recente",
        resolvido=False,
    ).exists()
    assert Alerta.objects.filter(
        tipo="rotina_leite",
        titulo="Vaca próxima da secagem",
        resolvido=False,
    ).exists()


@pytest.mark.django_db
def test_financeiro_alerta_entrega_sem_preco_e_pagamento_pendente() -> None:
    hoje = timezone.localdate()
    laticinio = Laticinio.objects.create(razao_social="Laticínio de teste")
    EntregaLeite.objects.create(
        laticinio=laticinio,
        data_coleta=timezone.now(),
        quantidade_litros=Decimal("100.000"),
        valor_litro=Decimal("0.0000"),
    )
    FechamentoLeite.objects.create(
        laticinio=laticinio,
        competencia=hoje.replace(day=1),
        data_inicial=hoje.replace(day=1),
        data_final=hoje,
        valor_liquido_calculado=Decimal("250.00"),
        data_prevista_pagamento=hoje + timedelta(days=5),
        situacao=FechamentoLeite.Situacao.FECHADO,
    )

    assert verificar_financeiro() == 2
    assert Alerta.objects.filter(titulo="Entrega sem preço", resolvido=False).exists()
    assert Alerta.objects.filter(
        titulo="Fechamento aguardando pagamento",
        resolvido=False,
    ).exists()


@pytest.mark.django_db
def test_conciliacao_alerta_diferencas_de_ordenha_e_destinos() -> None:
    hoje = timezone.localdate()
    Ordenha.objects.create(
        data=hoje,
        periodo=Ordenha.Periodo.MANHA,
        modo=Ordenha.Modo.INDIVIDUAL,
        quantidade_total="10.000",
        quantidade_vacas=1,
    )

    assert verificar_conciliacoes() == 2
    assert Alerta.objects.filter(
        titulo="Diferença entre produção individual e total",
        resolvido=False,
    ).exists()
    assert Alerta.objects.filter(
        titulo="Diferença entre produção e destinos",
        resolvido=False,
    ).exists()
