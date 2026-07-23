from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .backup_status import ler_backup_status
from .models import Alerta, ConfiguracaoSistema


@dataclass(frozen=True)
class AlertaProposto:
    chave: str
    tipo: str
    titulo: str
    mensagem: str
    nivel: str = Alerta.Nivel.ATENCAO
    entidade: str = ""
    identificador: str = ""
    data_referencia: date | None = None


@transaction.atomic
def sincronizar(tipo: str, propostas: Iterable[AlertaProposto]) -> int:
    propostas = list(propostas)
    chaves = {proposta.chave for proposta in propostas}
    Alerta.objects.filter(tipo=tipo, resolvido=False).exclude(chave__in=chaves).update(
        resolvido=True, resolvido_em=timezone.now()
    )
    for proposta in propostas:
        Alerta.objects.update_or_create(
            chave=proposta.chave,
            defaults={
                "tipo": proposta.tipo,
                "titulo": proposta.titulo,
                "mensagem": proposta.mensagem,
                "nivel": proposta.nivel,
                "entidade": proposta.entidade,
                "identificador": proposta.identificador,
                "data_referencia": proposta.data_referencia,
                "resolvido": False,
                "resolvido_em": None,
                "resolvido_por": None,
            },
        )
    return len(propostas)


def verificar_backup(*, agora: datetime | None = None) -> int:
    if not settings.BACKUP_MONITOR_ENABLED:
        return sincronizar("backup", [])

    momento = agora or timezone.now()
    status = ler_backup_status()
    proposta: AlertaProposto | None = None
    if status is None:
        proposta = AlertaProposto(
            chave="operacional:backup",
            tipo="backup",
            titulo="Nenhum backup confirmado",
            mensagem=(
                "Não existe um marcador válido de backup concluído. "
                "Execute e confira a rotina de backup."
            ),
            nivel=Alerta.Nivel.URGENTE,
            entidade="core.Backup",
            identificador="ultimo_backup",
            data_referencia=timezone.localdate(momento),
        )
    elif status.concluido_em > momento + timedelta(minutes=5):
        proposta = AlertaProposto(
            chave="operacional:backup",
            tipo="backup",
            titulo="Horário do backup inconsistente",
            mensagem=(
                "O último backup confirmado possui horário futuro. "
                "Confira o relógio do servidor e refaça o backup."
            ),
            nivel=Alerta.Nivel.URGENTE,
            entidade="core.Backup",
            identificador="ultimo_backup",
            data_referencia=timezone.localdate(momento),
        )
    else:
        limite = timedelta(hours=settings.BACKUP_MAX_AGE_HOURS)
        idade = momento - status.concluido_em
        if idade > limite:
            horario_local = timezone.localtime(status.concluido_em)
            proposta = AlertaProposto(
                chave="operacional:backup",
                tipo="backup",
                titulo="Backup atrasado",
                mensagem=(
                    f"O último backup confirmado foi {status.arquivo}, em "
                    f"{horario_local:%d/%m/%Y %H:%M}, e ultrapassou o limite de "
                    f"{settings.BACKUP_MAX_AGE_HOURS} hora(s)."
                ),
                nivel=Alerta.Nivel.URGENTE,
                entidade="core.Backup",
                identificador="ultimo_backup",
                data_referencia=timezone.localdate(status.concluido_em),
            )

    return sincronizar("backup", [proposta] if proposta else [])


def verificar_espaco_disco() -> int:
    if not settings.DISK_MONITOR_ENABLED:
        return sincronizar("espaco_disco", [])

    proposta: AlertaProposto | None = None
    try:
        uso = shutil.disk_usage(settings.DISK_MONITOR_PATH)
        percentual_livre = (uso.free / uso.total * 100) if uso.total > 0 else 0.0
    except OSError:
        proposta = AlertaProposto(
            chave="operacional:espaco-disco",
            tipo="espaco_disco",
            titulo="Espaço em disco não pôde ser verificado",
            mensagem=(
                "O volume configurado para monitoramento não está acessível. "
                "Confira a montagem e as permissões."
            ),
            nivel=Alerta.Nivel.URGENTE,
            entidade="core.Armazenamento",
            identificador="volume_monitorado",
            data_referencia=timezone.localdate(),
        )
    else:
        if percentual_livre < settings.DISK_MIN_FREE_PERCENT:
            gib_livres = uso.free / (1024**3)
            proposta = AlertaProposto(
                chave="operacional:espaco-disco",
                tipo="espaco_disco",
                titulo="Pouco espaço livre em disco",
                mensagem=(
                    f"O volume monitorado possui {percentual_livre:.1f}% livre "
                    f"({gib_livres:.1f} GiB), abaixo do limite de "
                    f"{settings.DISK_MIN_FREE_PERCENT}%."
                ),
                nivel=Alerta.Nivel.URGENTE,
                entidade="core.Armazenamento",
                identificador="volume_monitorado",
                data_referencia=timezone.localdate(),
            )

    return sincronizar("espaco_disco", [proposta] if proposta else [])


def verificar_partos() -> int:
    from apps.reproducao.models import Cobertura

    hoje = timezone.localdate()
    abertas = Cobertura.objects.select_related("vaca").filter(
        situacao=Cobertura.Situacao.PRENHEZ_CONFIRMADA
    )
    propostas: list[AlertaProposto] = []
    for cobertura in abertas:
        previsao = cobertura.previsao_atual_parto
        if not previsao:
            continue
        dias = (previsao - hoje).days
        if dias < 0:
            nivel, titulo = Alerta.Nivel.URGENTE, "Previsão de parto ultrapassada"
        elif dias <= 7:
            nivel, titulo = Alerta.Nivel.URGENTE, "Parto previsto nos próximos 7 dias"
        elif dias <= 30:
            nivel, titulo = Alerta.Nivel.ATENCAO, "Parto previsto nos próximos 30 dias"
        else:
            continue
        propostas.append(
            AlertaProposto(
                chave=f"parto:{cobertura.pk}:{previsao.isoformat()}",
                tipo="parto_previsto",
                titulo=titulo,
                mensagem=f"{cobertura.vaca} tem previsão para {previsao:%d/%m/%Y}.",
                nivel=nivel,
                entidade="reproducao.Cobertura",
                identificador=str(cobertura.pk),
                data_referencia=previsao,
            )
        )
    return sincronizar("parto_previsto", propostas)


def verificar_diagnosticos() -> int:
    from apps.reproducao.models import Cobertura

    config = ConfiguracaoSistema.obter()
    limite = timezone.localdate() - timedelta(days=config.dias_diagnostico)
    coberturas = Cobertura.objects.select_related("vaca").filter(
        situacao__in=[
            Cobertura.Situacao.REGISTRADA,
            Cobertura.Situacao.AGUARDANDO_CONFIRMACAO,
        ],
        data__lte=limite,
    )
    propostas = [
        AlertaProposto(
            chave=f"diagnostico:{item.pk}",
            tipo="cobertura_sem_diagnostico",
            titulo="Cobertura aguardando diagnóstico",
            mensagem=f"{item.vaca} foi coberta em {item.data:%d/%m/%Y}.",
            entidade="reproducao.Cobertura",
            identificador=str(item.pk),
            data_referencia=item.data,
        )
        for item in coberturas
    ]
    return sincronizar("cobertura_sem_diagnostico", propostas)


def verificar_carencias() -> int:
    from apps.saude.models import Tratamento

    agora = timezone.now()
    tratamentos = (
        Tratamento.objects.select_related("animal", "produto")
        .filter(
            data_liberacao__gt=agora,
        )
        .exclude(situacao=Tratamento.Situacao.CANCELADO)
    )
    propostas = [
        AlertaProposto(
            chave=f"carencia:{item.pk}:{item.data_liberacao.isoformat()}",
            tipo="carencia",
            titulo="Animal em período de carência",
            mensagem=(
                f"{item.animal}: {item.produto}. Liberação em "
                f"{timezone.localtime(item.data_liberacao):%d/%m/%Y %H:%M}."
            ),
            nivel=Alerta.Nivel.URGENTE,
            entidade="saude.Tratamento",
            identificador=str(item.pk),
            data_referencia=timezone.localdate(item.data_liberacao),
        )
        for item in tratamentos
    ]
    return sincronizar("carencia", propostas)


def verificar_queda_producao() -> int:
    from apps.leite.selectors import detectar_quedas_producao
    from apps.rebanho.models import Animal

    hoje = timezone.localdate()
    quedas = detectar_quedas_producao(data_referencia=hoje)
    vacas = Animal.objects.in_bulk(item["vaca_id"] for item in quedas)
    propostas: list[AlertaProposto] = []
    for queda in quedas:
        vaca_id = queda["vaca_id"]
        vaca = vacas.get(vaca_id)
        if vaca is None:
            continue
        propostas.append(
            AlertaProposto(
                chave=f"queda-producao:{vaca_id}:{hoje.isoformat()}",
                tipo="queda_producao",
                titulo="Redução de produção observada",
                mensagem=(
                    f"{vaca}: redução de {queda['queda_percentual']:.1f}% na média recente. "
                    "Este alerta não representa diagnóstico veterinário."
                ),
                entidade="rebanho.Animal",
                identificador=str(vaca_id),
                data_referencia=hoje,
            )
        )
    return sincronizar("queda_producao", propostas)


def verificar_rotina_leite() -> int:
    from django.db.models import Max

    from apps.lactacao.models import Lactacao
    from apps.leite.models import Ordenha, ProducaoAnimal
    from apps.reproducao.models import Cobertura

    hoje = timezone.localdate()
    configuracao = ConfiguracaoSistema.obter()
    limite_ordenha = hoje - timedelta(days=configuracao.dias_sem_ordenha_alerta)
    lactacoes = list(
        Lactacao.objects.filter(situacao=Lactacao.Situacao.ATIVA).select_related("vaca")
    )
    ultimas = {
        item["lactacao_id"]: item["ultima"]
        for item in ProducaoAnimal.objects.filter(lactacao__in=lactacoes)
        .exclude(ordenha__situacao=Ordenha.Situacao.CANCELADA)
        .values("lactacao_id")
        .annotate(ultima=Max("ordenha__data"))
    }
    propostas: list[AlertaProposto] = []
    for lactacao in lactacoes:
        ultima = ultimas.get(lactacao.pk)
        if lactacao.data_inicio <= limite_ordenha and (ultima is None or ultima < limite_ordenha):
            referencia = ultima or lactacao.data_inicio
            propostas.append(
                AlertaProposto(
                    chave=f"rotina-leite:sem-ordenha:{lactacao.pk}",
                    tipo="rotina_leite",
                    titulo="Vaca sem ordenha recente",
                    mensagem=(
                        f"{lactacao.vaca} não possui produção individual registrada desde "
                        f"{referencia:%d/%m/%Y}."
                    ),
                    entidade="lactacao.Lactacao",
                    identificador=str(lactacao.pk),
                    data_referencia=referencia,
                )
            )

    limite_secagem = hoje + timedelta(days=configuracao.antecedencia_alerta_secagem_dias)
    vacas_ativas = {item.vaca_id for item in lactacoes}
    gestacoes = (
        Cobertura.objects.filter(
            vaca_id__in=vacas_ativas,
            situacao=Cobertura.Situacao.PRENHEZ_CONFIRMADA,
            previsao_atual_parto__isnull=False,
        )
        .select_related("vaca")
        .order_by("vaca_id", "-data", "-criado_em")
    )
    vacas_processadas: set[object] = set()
    for cobertura in gestacoes:
        if cobertura.vaca_id in vacas_processadas:
            continue
        vacas_processadas.add(cobertura.vaca_id)
        previsao_parto = cobertura.previsao_atual_parto
        if previsao_parto is None:
            continue
        data_secagem = previsao_parto - timedelta(days=configuracao.dias_secagem)
        if data_secagem > limite_secagem:
            continue
        atrasada = data_secagem < hoje
        propostas.append(
            AlertaProposto(
                chave=f"rotina-leite:secagem:{cobertura.pk}:{data_secagem.isoformat()}",
                tipo="rotina_leite",
                titulo=(
                    "Secagem recomendada ultrapassada" if atrasada else "Vaca próxima da secagem"
                ),
                mensagem=(
                    f"{cobertura.vaca}: secagem recomendada para {data_secagem:%d/%m/%Y}, "
                    f"considerando parto previsto em {previsao_parto:%d/%m/%Y}."
                ),
                nivel=Alerta.Nivel.URGENTE if atrasada else Alerta.Nivel.ATENCAO,
                entidade="reproducao.Cobertura",
                identificador=str(cobertura.pk),
                data_referencia=data_secagem,
            )
        )
    return sincronizar("rotina_leite", propostas)


def verificar_conciliacoes() -> int:
    from apps.financeiro.selectors import conferencia_mensal
    from apps.leite.models import DestinoLeite, Ordenha
    from apps.leite.selectors import conciliacao_dia

    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=6)
    configuracao = ConfiguracaoSistema.obter()
    propostas: list[AlertaProposto] = []
    ordenhas = (
        Ordenha.objects.filter(
            data__range=(inicio, hoje),
            modo=Ordenha.Modo.INDIVIDUAL,
        )
        .exclude(situacao=Ordenha.Situacao.CANCELADA)
        .prefetch_related("producoes")
    )
    for ordenha in ordenhas:
        diferenca = ordenha.diferenca_individual
        excede = (
            abs(diferenca) > configuracao.tolerancia_divergencia_litros
            or ordenha.diferenca_percentual > configuracao.tolerancia_divergencia_percentual
        )
        if excede and not ordenha.justificativa_divergencia.strip():
            propostas.append(
                AlertaProposto(
                    chave=f"conciliacao:ordenha:{ordenha.pk}",
                    tipo="conciliacao",
                    titulo="Diferença entre produção individual e total",
                    mensagem=(
                        f"Ordenha de {ordenha.data:%d/%m/%Y}: diferença de "
                        f"{diferenca:.3f} L ({ordenha.diferenca_percentual:.2f}%)."
                    ),
                    entidade="leite.Ordenha",
                    identificador=str(ordenha.pk),
                    data_referencia=ordenha.data,
                )
            )

    dias = set(
        Ordenha.objects.filter(data__range=(inicio, hoje))
        .exclude(situacao=Ordenha.Situacao.CANCELADA)
        .values_list("data", flat=True)
    )
    dias.update(
        DestinoLeite.objects.filter(data__range=(inicio, hoje)).values_list("data", flat=True)
    )
    for dia in sorted(dias):
        conciliacao = conciliacao_dia(dia=dia)
        diferenca = conciliacao["diferenca"]
        percentual = (
            abs(diferenca) / conciliacao["produzido"] * 100
            if conciliacao["produzido"]
            else Decimal("0")
        )
        if (
            abs(diferenca) <= configuracao.tolerancia_divergencia_litros
            and percentual <= configuracao.tolerancia_divergencia_percentual
        ):
            continue
        propostas.append(
            AlertaProposto(
                chave=f"conciliacao:producao-destinos:{dia.isoformat()}",
                tipo="conciliacao",
                titulo="Diferença entre produção e destinos",
                mensagem=(
                    f"Em {dia:%d/%m/%Y}, foram produzidos "
                    f"{conciliacao['produzido']:.3f} L e destinados "
                    f"{conciliacao['destinado']:.3f} L; diferença de {diferenca:.3f} L."
                ),
                entidade="leite.DestinoLeite",
                identificador=dia.isoformat(),
                data_referencia=dia,
            )
        )

    conferencia = conferencia_mensal(ano=hoje.year, mes=hoje.month)
    diferenca_entrega = conferencia["diferenca_destinado_entregue"]
    if abs(diferenca_entrega) > configuracao.tolerancia_divergencia_litros:
        propostas.append(
            AlertaProposto(
                chave=f"conciliacao:destinado-entregue:{hoje:%Y-%m}",
                tipo="conciliacao",
                titulo="Diferença entre leite destinado e entregue",
                mensagem=(
                    f"No mês, {conferencia['destinado_laticinio']:.3f} L foram destinados "
                    f"ao laticínio e {conferencia['entregue']:.3f} L foram entregues; "
                    f"diferença de {diferenca_entrega:.3f} L."
                ),
                entidade="financeiro.EntregaLeite",
                identificador=f"{hoje:%Y-%m}",
                data_referencia=hoje.replace(day=1),
            )
        )
    return sincronizar("conciliacao", propostas)


def verificar_financeiro() -> int:
    from apps.financeiro.models import EntregaLeite, FechamentoLeite

    hoje = timezone.localdate()
    entregas_sem_preco = EntregaLeite.objects.filter(
        ativo_registro=True,
        valor_litro=0,
    ).exclude(situacao=EntregaLeite.Situacao.CANCELADA)
    fechamentos = FechamentoLeite.objects.select_related("laticinio").exclude(
        situacao__in=[FechamentoLeite.Situacao.PAGO, FechamentoLeite.Situacao.CANCELADO]
    )
    propostas = [
        AlertaProposto(
            chave=f"entrega-sem-preco:{entrega.pk}",
            tipo="financeiro",
            titulo="Entrega sem preço",
            mensagem=(
                f"A entrega de {entrega.quantidade_litros:.3f} L em "
                f"{timezone.localtime(entrega.data_coleta):%d/%m/%Y} está com preço zerado."
            ),
            nivel=Alerta.Nivel.URGENTE,
            entidade="financeiro.EntregaLeite",
            identificador=str(entrega.pk),
            data_referencia=timezone.localdate(entrega.data_coleta),
        )
        for entrega in entregas_sem_preco
    ]
    for fechamento in fechamentos:
        if fechamento.situacao == FechamentoLeite.Situacao.DIVERGENTE:
            propostas.append(
                AlertaProposto(
                    chave=f"divergencia-fechamento:{fechamento.pk}",
                    tipo="financeiro",
                    titulo="Fechamento com divergência",
                    mensagem=(
                        f"A competência {fechamento.competencia:%m/%Y} precisa de conferência."
                    ),
                    nivel=Alerta.Nivel.URGENTE,
                    entidade="financeiro.FechamentoLeite",
                    identificador=str(fechamento.pk),
                    data_referencia=fechamento.competencia,
                )
            )
        if fechamento.data_prevista_pagamento and fechamento.data_prevista_pagamento < hoje:
            propostas.append(
                AlertaProposto(
                    chave=f"pagamento-atrasado:{fechamento.pk}",
                    tipo="financeiro",
                    titulo="Pagamento atrasado",
                    mensagem=(
                        f"Saldo de R$ {fechamento.saldo:.2f} previsto para "
                        f"{fechamento.data_prevista_pagamento:%d/%m/%Y}."
                    ),
                    nivel=Alerta.Nivel.URGENTE,
                    entidade="financeiro.FechamentoLeite",
                    identificador=str(fechamento.pk),
                    data_referencia=fechamento.data_prevista_pagamento,
                )
            )
        elif (
            fechamento.situacao
            in [
                FechamentoLeite.Situacao.FECHADO,
                FechamentoLeite.Situacao.PARCIALMENTE_PAGO,
            ]
            and fechamento.saldo > 0
        ):
            propostas.append(
                AlertaProposto(
                    chave=f"aguardando-pagamento:{fechamento.pk}",
                    tipo="financeiro",
                    titulo="Fechamento aguardando pagamento",
                    mensagem=(
                        f"A competência {fechamento.competencia:%m/%Y} possui saldo de "
                        f"R$ {fechamento.saldo:.2f}."
                    ),
                    entidade="financeiro.FechamentoLeite",
                    identificador=str(fechamento.pk),
                    data_referencia=fechamento.data_prevista_pagamento or fechamento.data_final,
                )
            )
    return sincronizar("financeiro", propostas)


def verificar_todos() -> dict[str, int]:
    return {
        "backup": verificar_backup(),
        "espaco_disco": verificar_espaco_disco(),
        "partos": verificar_partos(),
        "diagnosticos": verificar_diagnosticos(),
        "carencias": verificar_carencias(),
        "queda_producao": verificar_queda_producao(),
        "rotina_leite": verificar_rotina_leite(),
        "conciliacao": verificar_conciliacoes(),
        "financeiro": verificar_financeiro(),
    }
