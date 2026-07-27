from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .services import SecaoRelatorio, resposta_pdf, resposta_xlsx

TRACO = "—"
ZERO_LITROS = Decimal("0.000")
ZERO_DINHEIRO = Decimal("0.00")


def _periodo(request: HttpRequest) -> tuple[date, date]:
    hoje = timezone.localdate()
    inicio_padrao = hoje.replace(day=1)
    try:
        inicio = date.fromisoformat(request.GET.get("inicio", ""))
    except ValueError:
        inicio = inicio_padrao
    try:
        fim = date.fromisoformat(request.GET.get("fim", ""))
    except ValueError:
        fim = hoje
    if inicio > fim:
        inicio, fim = fim, inicio
    return inicio, fim


def _data_br(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else TRACO


def _litros(valor: Decimal | int | None) -> str:
    return f"{Decimal(valor or 0):.3f}"


def _percentual(valor: Decimal | int | None) -> str:
    return f"{Decimal(valor or 0):.2f}%"


def _identificador(dados: dict[str, Any], prefixo: str) -> str:
    return (
        dados.get(f"{prefixo}identificacao")
        or dados.get(f"{prefixo}identificacao_provisoria")
        or dados.get(f"{prefixo}nome")
        or TRACO
    )


def _uuid_valido(valor: str) -> bool:
    try:
        UUID(valor)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _filtro_select(
    nome: str,
    rotulo: str,
    opcoes: Sequence[tuple[object, object]],
    atual: str,
) -> dict[str, object]:
    return {"nome": nome, "rotulo": rotulo, "opcoes": opcoes, "atual": atual}


def _responder(
    request: HttpRequest,
    *,
    nome: str,
    titulo: str,
    secoes: list[SecaoRelatorio],
    contexto: dict[str, object],
) -> HttpResponse:
    formato = request.GET.get("formato", "tela")
    if formato == "xlsx":
        return resposta_xlsx(nome, titulo, secoes=secoes)
    if formato == "pdf":
        return resposta_pdf(nome, titulo, contexto=contexto, secoes=secoes)
    query_export = request.GET.copy()
    query_export.pop("formato", None)
    primeira = secoes[0] if secoes else {"cabecalhos": (), "linhas": ()}
    return render(
        request,
        "relatorios/tabela.html",
        {
            "titulo": titulo,
            "secoes": secoes,
            "cabecalhos": primeira["cabecalhos"],
            "linhas": primeira["linhas"],
            "query_export": query_export.urlencode(),
            **contexto,
        },
    )


@login_required
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "relatorios/index.html")


@login_required
def rebanho(request: HttpRequest) -> HttpResponse:
    from apps.rebanho.models import Animal, Pesagem

    ultima_pesagem = Pesagem.objects.filter(animal_id=OuterRef("pk")).order_by(
        "-data", "-criado_em"
    )
    animais = Animal.objects.select_related("raca", "lote", "mae", "pai").annotate(
        ultimo_peso=Subquery(ultima_pesagem.values("peso_kg")[:1]),
        data_ultimo_peso=Subquery(ultima_pesagem.values("data")[:1]),
    )
    sexo = request.GET.get("sexo", "")
    situacao = request.GET.get("situacao", "")
    categoria = request.GET.get("categoria", "")
    if sexo in Animal.Sexo.values:
        animais = animais.filter(sexo=sexo)
    else:
        sexo = ""
    if situacao in Animal.Situacao.values:
        animais = animais.filter(situacao=situacao)
    else:
        situacao = ""

    categorias = {
        "BEZERRO": "Bezerro",
        "NOVILHA": "Novilha",
        "VACA": "Vaca",
        "BOI": "Boi",
    }
    if categoria not in categorias:
        categoria = ""
    if categoria:
        animais = animais.filter(tipo_animal=categoria)
    objetos = list(animais)

    linhas: list[Sequence[object]] = []
    for animal in objetos:
        peso = animal.ultimo_peso if animal.ultimo_peso is not None else animal.peso_atual
        linhas.append(
            (
                animal.identificador_exibicao,
                animal.nome or TRACO,
                animal.get_sexo_display(),
                animal.categoria,
                _data_br(animal.data_nascimento),
                animal.idade,
                animal.mae.identificador_exibicao if animal.mae else "Desconhecida",
                animal.pai.identificador_exibicao if animal.pai else "Desconhecido",
                str(animal.raca or TRACO),
                str(animal.lote or TRACO),
                f"{peso:.2f} kg" if peso is not None else TRACO,
                _data_br(animal.data_ultimo_peso),
                animal.get_situacao_display(),
            )
        )
    secoes: list[SecaoRelatorio] = [
        {
            "titulo": "Animais, filiação e última pesagem",
            "cabecalhos": (
                "Identificação",
                "Nome",
                "Sexo",
                "Tipo de animal",
                "Nascimento",
                "Idade",
                "Mãe",
                "Pai",
                "Raça",
                "Lote",
                "Último peso",
                "Data da pesagem",
                "Situação",
            ),
            "linhas": linhas,
            "resumo": f"{len(linhas)} animal(is)",
        }
    ]
    filtros = [
        _filtro_select("sexo", "Sexo", Animal.Sexo.choices, sexo),
        _filtro_select("situacao", "Situação", Animal.Situacao.choices, situacao),
        _filtro_select("categoria", "Tipo de animal", tuple(categorias.items()), categoria),
    ]
    return _responder(
        request,
        nome="relatorio-rebanho",
        titulo="Relatório do rebanho",
        secoes=secoes,
        contexto={
            "total": f"{len(linhas)} animal(is)",
            "filtros_periodo": False,
            "filtros": filtros,
        },
    )


@login_required
def reproducao(request: HttpRequest) -> HttpResponse:
    from apps.reproducao.models import Cobertura, DiagnosticoGestacao, Parto, PerdaGestacional

    inicio, fim = _periodo(request)
    evento = request.GET.get("evento", "")
    eventos = (
        ("coberturas", "Coberturas"),
        ("diagnosticos", "Diagnósticos"),
        ("partos", "Partos"),
        ("perdas", "Perdas gestacionais"),
        ("intervalos", "Intervalos entre partos"),
    )
    if evento not in {valor for valor, _ in eventos}:
        evento = ""

    coberturas = list(
        Cobertura.objects.select_related("vaca", "touro")
        .filter(data__range=(inicio, fim))
        .exclude(situacao=Cobertura.Situacao.CANCELADA)
    )
    linhas_coberturas = [
        (
            _data_br(item.data),
            item.vaca.identificador_exibicao,
            item.touro.identificador_exibicao if item.touro else "Desconhecido",
            item.get_tipo_display(),
            item.get_forma_identificacao_display(),
            item.get_situacao_display(),
            _data_br(item.previsao_original_parto),
            _data_br(item.previsao_atual_parto),
            (
                f"{_data_br(item.inicio_intervalo_parto)} a {_data_br(item.fim_intervalo_parto)}"
                if item.intervalo_provavel
                else TRACO
            ),
        )
        for item in coberturas
    ]

    diagnosticos = list(
        DiagnosticoGestacao.objects.select_related("vaca", "cobertura").filter(
            data__range=(inicio, fim),
            cobertura__ativo_registro=True,
        )
        if hasattr(Cobertura, "ativo_registro")
        else DiagnosticoGestacao.objects.select_related("vaca", "cobertura")
        .filter(data__range=(inicio, fim))
        .exclude(cobertura__situacao=Cobertura.Situacao.CANCELADA)
    )
    # Cobertura preserva histórico por situação, não possui exclusão lógica própria.
    diagnosticos = [
        item for item in diagnosticos if item.cobertura.situacao != Cobertura.Situacao.CANCELADA
    ]
    linhas_diagnosticos = [
        (
            _data_br(item.data),
            item.vaca.identificador_exibicao,
            _data_br(item.cobertura.data),
            item.get_resultado_display(),
            item.get_metodo_display(),
            (
                f"{item.idade_gestacional_estimada_dias} dias"
                if item.idade_gestacional_estimada_dias is not None
                else TRACO
            ),
            _data_br(item.nova_previsao_parto),
            item.responsavel or TRACO,
        )
        for item in diagnosticos
    ]

    partos = list(
        Parto.objects.select_related("vaca", "cobertura")
        .filter(data_hora__date__range=(inicio, fim))
        .exclude(situacao=Parto.Situacao.CANCELADO)
    )
    linhas_partos = [
        (
            timezone.localtime(item.data_hora).strftime("%d/%m/%Y %H:%M"),
            item.vaca.identificador_exibicao,
            _data_br(item.cobertura.data) if item.cobertura else TRACO,
            item.get_resultado_display(),
            item.quantidade_bezerros,
            "Sim" if item.necessitou_auxilio else "Não",
            item.responsavel or TRACO,
            item.get_situacao_display(),
        )
        for item in partos
    ]

    perdas = list(
        PerdaGestacional.objects.select_related("vaca", "cobertura")
        .filter(data__range=(inicio, fim))
        .exclude(cobertura__situacao=Cobertura.Situacao.CANCELADA)
    )
    linhas_perdas = [
        (
            _data_br(item.data),
            item.vaca.identificador_exibicao,
            _data_br(item.cobertura.data),
            item.get_tipo_display(),
            item.responsavel or TRACO,
            item.observacoes or TRACO,
        )
        for item in perdas
    ]

    linhas_intervalos: list[Sequence[object]] = []
    vacas_alvo = {item.vaca_id for item in partos}
    if vacas_alvo:
        anteriores: dict[object, Parto] = {}
        for item in (
            Parto.objects.select_related("vaca")
            .filter(vaca_id__in=vacas_alvo, data_hora__date__lte=fim)
            .exclude(situacao=Parto.Situacao.CANCELADO)
            .order_by("vaca_id", "data_hora")
        ):
            anterior = anteriores.get(item.vaca_id)
            if item in partos and anterior:
                data_item = timezone.localtime(item.data_hora).date()
                data_anterior = timezone.localtime(anterior.data_hora).date()
                linhas_intervalos.append(
                    (
                        item.vaca.identificador_exibicao,
                        _data_br(data_anterior),
                        _data_br(data_item),
                        (data_item - data_anterior).days,
                    )
                )
            anteriores[item.vaca_id] = item

    secoes_disponiveis: list[tuple[str, SecaoRelatorio]] = [
        (
            "coberturas",
            {
                "titulo": "Coberturas e previsões",
                "cabecalhos": (
                    "Data",
                    "Vaca",
                    "Touro",
                    "Tipo",
                    "Identificação",
                    "Situação",
                    "Previsão original",
                    "Previsão atual",
                    "Intervalo provável",
                ),
                "linhas": linhas_coberturas,
                "resumo": f"{len(linhas_coberturas)} cobertura(s)",
            },
        ),
        (
            "diagnosticos",
            {
                "titulo": "Diagnósticos de gestação",
                "cabecalhos": (
                    "Data",
                    "Vaca",
                    "Cobertura",
                    "Resultado",
                    "Método",
                    "Idade gestacional",
                    "Nova previsão",
                    "Responsável",
                ),
                "linhas": linhas_diagnosticos,
                "resumo": f"{len(linhas_diagnosticos)} diagnóstico(s)",
            },
        ),
        (
            "partos",
            {
                "titulo": "Partos",
                "cabecalhos": (
                    "Data e hora",
                    "Vaca",
                    "Cobertura",
                    "Resultado",
                    "Bezerros",
                    "Auxílio",
                    "Responsável",
                    "Situação",
                ),
                "linhas": linhas_partos,
                "resumo": f"{len(linhas_partos)} parto(s)",
            },
        ),
        (
            "perdas",
            {
                "titulo": "Perdas gestacionais",
                "cabecalhos": (
                    "Data",
                    "Vaca",
                    "Cobertura",
                    "Tipo",
                    "Responsável",
                    "Observações",
                ),
                "linhas": linhas_perdas,
                "resumo": f"{len(linhas_perdas)} perda(s)",
            },
        ),
        (
            "intervalos",
            {
                "titulo": "Intervalos entre partos",
                "cabecalhos": ("Vaca", "Parto anterior", "Parto atual", "Intervalo (dias)"),
                "linhas": linhas_intervalos,
                "resumo": f"{len(linhas_intervalos)} intervalo(s)",
            },
        ),
    ]
    secoes = [secao for chave, secao in secoes_disponiveis if not evento or chave == evento]
    total = (
        f"{len(linhas_coberturas)} cobertura(s) · {len(linhas_diagnosticos)} diagnóstico(s) · "
        f"{len(linhas_partos)} parto(s) · {len(linhas_perdas)} perda(s)"
    )
    return _responder(
        request,
        nome=f"reproducao-{inicio:%Y-%m}",
        titulo="Histórico reprodutivo",
        secoes=secoes,
        contexto={
            "inicio": inicio,
            "fim": fim,
            "total": total,
            "filtros_periodo": True,
            "filtros": [_filtro_select("evento", "Evento", eventos, evento)],
        },
    )


@login_required
def leite(request: HttpRequest) -> HttpResponse:
    from apps.leite.models import Ordenha

    inicio, fim = _periodo(request)
    ordenhas = (
        Ordenha.objects.filter(
            data__range=(inicio, fim),
            ativo_registro=True,
        )
        .exclude(situacao=Ordenha.Situacao.CANCELADA)
        .order_by("data")
    )
    diarios = list(ordenhas.values("data").annotate(total=Sum("quantidade_total")).order_by("data"))
    total = sum((Decimal(item["total"] or 0) for item in diarios), ZERO_LITROS)
    media = (total / Decimal(len(diarios))).quantize(Decimal("0.001")) if diarios else ZERO_LITROS
    linhas = [(_data_br(item["data"]), _litros(item["total"])) for item in diarios]
    secoes: list[SecaoRelatorio] = [
        {
            "titulo": "Leite por dia",
            "cabecalhos": ("Data", "Litros"),
            "linhas": linhas,
            "resumo": f"Total: {_litros(total)} L",
        }
    ]
    return _responder(
        request,
        nome=f"leite-{inicio:%Y-%m}",
        titulo="Relatório de leite",
        secoes=secoes,
        contexto={
            "inicio": inicio,
            "fim": fim,
            "total": (f"Total: {_litros(total)} L · Média por dia registrado: {_litros(media)} L"),
            "filtros_periodo": True,
            "filtros": [],
        },
    )


def _leite_detalhado(request: HttpRequest) -> HttpResponse:
    from apps.leite.models import DestinoLeite, Ordenha, ProducaoAnimal
    from apps.rebanho.models import Lote

    inicio, fim = _periodo(request)
    periodo = request.GET.get("periodo", "")
    lote = request.GET.get("lote", "")
    ordenhas = (
        Ordenha.objects.select_related("lote")
        .filter(data__range=(inicio, fim), ativo_registro=True)
        .exclude(situacao=Ordenha.Situacao.CANCELADA)
    )
    if periodo in Ordenha.Periodo.values:
        ordenhas = ordenhas.filter(periodo=periodo)
    else:
        periodo = ""
    if lote and _uuid_valido(lote):
        ordenhas = ordenhas.filter(lote_id=lote)
    else:
        lote = ""

    ordenhas = ordenhas.annotate(
        total_individual_relatorio=Coalesce(
            Sum("producoes__quantidade_litros"),
            ZERO_LITROS,
            output_field=DecimalField(max_digits=14, decimal_places=3),
        )
    )
    linhas_ordenhas: list[Sequence[object]] = []
    for item in ordenhas:
        total_individual = item.total_individual_relatorio or ZERO_LITROS
        diferenca = (item.quantidade_total - total_individual).quantize(Decimal("0.001"))
        percentual = (
            (abs(diferenca) / item.quantidade_total * Decimal("100")).quantize(Decimal("0.01"))
            if item.quantidade_total
            else ZERO_DINHEIRO
        )
        linhas_ordenhas.append(
            (
                _data_br(item.data),
                item.get_periodo_display(),
                item.get_modo_display(),
                _litros(item.quantidade_total),
                _litros(total_individual),
                _litros(diferenca),
                _percentual(percentual),
                item.quantidade_vacas,
                str(item.lote or TRACO),
                item.get_situacao_display(),
            )
        )

    diarios = list(
        ordenhas.values("data")
        .annotate(
            total=Sum("quantidade_total"),
            quantidade_ordenhas=Count("id", distinct=True),
            vacas=Sum("quantidade_vacas"),
        )
        .order_by("data")
    )
    linhas_diarias = [
        (
            _data_br(item["data"]),
            _litros(item["total"]),
            item["quantidade_ordenhas"],
            item["vacas"] or 0,
        )
        for item in diarios
    ]

    producoes = ProducaoAnimal.objects.filter(ordenha__in=ordenhas)
    por_vaca = list(
        producoes.values(
            "vaca__identificacao",
            "vaca__identificacao_provisoria",
            "vaca__nome",
        )
        .annotate(
            total=Sum("quantidade_litros"),
            dias=Count("ordenha__data", distinct=True),
            ordenhas=Count("ordenha", distinct=True),
        )
        .order_by("vaca__identificacao", "vaca__identificacao_provisoria")
    )
    linhas_vacas: list[Sequence[object]] = []
    for item in por_vaca:
        total_vaca = Decimal(item["total"] or 0)
        dias = int(item["dias"] or 0)
        media = (total_vaca / Decimal(dias)).quantize(Decimal("0.001")) if dias else ZERO_LITROS
        linhas_vacas.append(
            (
                _identificador(item, "vaca__"),
                item["vaca__nome"] or TRACO,
                _litros(total_vaca),
                dias,
                item["ordenhas"],
                _litros(media),
            )
        )

    por_lote = list(
        ordenhas.values("lote__nome")
        .annotate(total=Sum("quantidade_total"), quantidade=Count("id", distinct=True))
        .order_by("lote__nome")
    )
    linhas_lotes = [
        (item["lote__nome"] or "Sem lote", _litros(item["total"]), item["quantidade"])
        for item in por_lote
    ]

    destinos = DestinoLeite.objects.filter(data__range=(inicio, fim)).filter(
        Q(ordenha__isnull=True) | Q(ordenha__in=ordenhas)
    )
    por_destino = list(
        destinos.values("tipo")
        .annotate(total=Sum("quantidade_litros"), registros=Count("id"))
        .order_by("tipo")
    )
    rotulos_destino = dict(DestinoLeite.Tipo.choices)
    linhas_destinos = [
        (rotulos_destino[item["tipo"]], _litros(item["total"]), item["registros"])
        for item in por_destino
    ]

    destinos_diarios = {
        item["data"]: Decimal(item["total"] or 0)
        for item in destinos.values("data").annotate(total=Sum("quantidade_litros"))
    }
    producao_diaria = {item["data"]: Decimal(item["total"] or 0) for item in diarios}
    linhas_divergencias = []
    for dia in sorted(set(producao_diaria) | set(destinos_diarios)):
        produzido = producao_diaria.get(dia, ZERO_LITROS)
        destinado = destinos_diarios.get(dia, ZERO_LITROS)
        diferenca = (produzido - destinado).quantize(Decimal("0.001"))
        percentual = (
            (abs(diferenca) / produzido * Decimal("100")).quantize(Decimal("0.01"))
            if produzido
            else ZERO_DINHEIRO
        )
        linhas_divergencias.append(
            (
                _data_br(dia),
                _litros(produzido),
                _litros(destinado),
                _litros(diferenca),
                _percentual(percentual),
            )
        )

    total_produzido = sum(producao_diaria.values(), ZERO_LITROS)
    total_destinado = sum(destinos_diarios.values(), ZERO_LITROS)
    total_individual = sum((Decimal(item["total"] or 0) for item in por_vaca), ZERO_LITROS)
    secoes: list[SecaoRelatorio] = [
        {
            "titulo": "Produção diária",
            "cabecalhos": ("Data", "Litros", "Ordenhas", "Vacas informadas"),
            "linhas": linhas_diarias,
            "resumo": f"Total: {_litros(total_produzido)} L",
        },
        {
            "titulo": "Ordenhas e conciliação individual",
            "cabecalhos": (
                "Data",
                "Período",
                "Modo",
                "Total (L)",
                "Individual (L)",
                "Diferença (L)",
                "Diferença (%)",
                "Vacas",
                "Lote",
                "Situação",
            ),
            "linhas": linhas_ordenhas,
            "resumo": f"{len(linhas_ordenhas)} ordenha(s)",
        },
        {
            "titulo": "Produção por vaca",
            "cabecalhos": ("Vaca", "Nome", "Litros", "Dias", "Ordenhas", "Média diária (L)"),
            "linhas": linhas_vacas,
            "resumo": f"Total individual: {_litros(total_individual)} L",
        },
        {
            "titulo": "Produção por lote",
            "cabecalhos": ("Lote", "Litros", "Ordenhas"),
            "linhas": linhas_lotes,
        },
        {
            "titulo": "Destinos do leite",
            "cabecalhos": ("Destino", "Litros", "Registros"),
            "linhas": linhas_destinos,
            "resumo": f"Total destinado: {_litros(total_destinado)} L",
        },
        {
            "titulo": "Divergências produção × destinos",
            "cabecalhos": (
                "Data",
                "Produzido (L)",
                "Destinado (L)",
                "Diferença (L)",
                "Diferença (%)",
            ),
            "linhas": linhas_divergencias,
            "resumo": f"Diferença do período: {_litros(total_produzido - total_destinado)} L",
        },
    ]
    lotes = tuple((str(item.pk), item.nome) for item in Lote.objects.order_by("nome"))
    return _responder(
        request,
        nome=f"producao-leite-{inicio:%Y-%m}",
        titulo="Produção de leite",
        secoes=secoes,
        contexto={
            "inicio": inicio,
            "fim": fim,
            "total": (
                f"Produzido: {_litros(total_produzido)} L · Destinado: "
                f"{_litros(total_destinado)} L · Diferença: "
                f"{_litros(total_produzido - total_destinado)} L"
            ),
            "filtros_periodo": True,
            "filtros": [
                _filtro_select("periodo", "Período da ordenha", Ordenha.Periodo.choices, periodo),
                _filtro_select("lote", "Lote", lotes, lote),
            ],
        },
    )
