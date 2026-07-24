from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from .models import Animal, Lote, Pesagem


def listar_animais(
    *,
    busca: str = "",
    situacao: str = "",
    sexo: str = "",
    tipo_animal: str = "",
    lote_id: str = "",
) -> QuerySet[Animal]:
    from apps.reproducao.models import Cobertura

    ultima_cobertura = (
        Cobertura.objects.filter(vaca_id=OuterRef("pk"))
        .order_by("-data", "-criado_em")
        .values("data")[:1]
    )
    queryset = Animal.objects.select_related("raca", "lote", "mae", "pai").annotate(
        data_ultima_cobertura=Subquery(ultima_cobertura)
    )
    if busca := busca.strip():
        queryset = queryset.filter(
            Q(identificacao__icontains=busca)
            | Q(identificacao_provisoria__icontains=busca)
            | Q(nome__icontains=busca)
        )
    if situacao in Animal.Situacao.values:
        queryset = queryset.filter(situacao=situacao)
    if sexo in Animal.Sexo.values:
        queryset = queryset.filter(sexo=sexo)
    if tipo_animal in Animal.TipoAnimal.values:
        queryset = queryset.filter(tipo_animal=tipo_animal)
    if lote_id:
        queryset = queryset.filter(lote_id=lote_id)
    return queryset.order_by("identificacao", "identificacao_provisoria", "nome")


def obter_animal(*, animal_id: str) -> Animal:
    return (
        Animal.objects.select_related("raca", "lote", "mae", "pai")
        .prefetch_related(
            "filhos_como_mae",
            "filhos_como_pai",
            "pesagens",
            "movimentacoes_lote__lote_anterior",
            "movimentacoes_lote__novo_lote",
            "historico_parentesco",
            "coberturas",
            "diagnosticos_gestacao",
            "partos",
            "lactacoes",
        )
        .get(pk=animal_id)
    )


def listar_lotes_ativos() -> QuerySet[Lote]:
    return Lote.objects.filter(ativo=True).annotate(
        quantidade_animais=Count("animais", filter=Q(animais__situacao=Animal.Situacao.ATIVO))
    )


def evolucao_peso(
    *, animal: Animal, inicio: date | None = None, fim: date | None = None
) -> QuerySet[Pesagem]:
    queryset = animal.pesagens.order_by("data", "criado_em")
    if inicio:
        queryset = queryset.filter(data__gte=inicio)
    if fim:
        queryset = queryset.filter(data__lte=fim)
    return queryset


def resumo_rebanho() -> dict[str, int]:
    valores = Animal.objects.aggregate(
        total=Count("id"),
        ativos=Count("id", filter=Q(situacao=Animal.Situacao.ATIVO)),
        femeas_ativas=Count(
            "id",
            filter=Q(situacao=Animal.Situacao.ATIVO, sexo=Animal.Sexo.FEMEA),
        ),
        machos_ativos=Count(
            "id",
            filter=Q(situacao=Animal.Situacao.ATIVO, sexo=Animal.Sexo.MACHO),
        ),
    )
    return {chave: int(valor or 0) for chave, valor in valores.items()}


def linha_do_tempo(
    *,
    animal: Animal,
    tipo: str = "",
    inicio: date | None = None,
    fim: date | None = None,
) -> list[dict[str, Any]]:
    def momento(valor: date | datetime) -> datetime:
        if isinstance(valor, datetime):
            return (
                timezone.localtime(valor)
                if timezone.is_aware(valor)
                else timezone.make_aware(valor, timezone.get_current_timezone())
            )
        return timezone.make_aware(
            datetime.combine(valor, time.min), timezone.get_current_timezone()
        )

    eventos: list[dict[str, Any]] = [
        {
            "data": animal.criado_em,
            "tipo": "cadastro",
            "titulo": "Animal cadastrado",
            "descricao": animal.identificador_exibicao,
        }
    ]
    eventos.extend(
        {
            "data": momento(movimento.data),
            "tipo": "lote",
            "titulo": "Mudança de lote",
            "descricao": f"{movimento.lote_anterior or 'Sem lote'} → "
            f"{movimento.novo_lote or 'Sem lote'}",
        }
        for movimento in animal.movimentacoes_lote.all()
    )
    eventos.extend(
        {
            "data": momento(pesagem.data),
            "tipo": "pesagem",
            "titulo": "Pesagem",
            "descricao": f"{pesagem.peso_kg} kg",
        }
        for pesagem in animal.pesagens.all()
    )
    if animal.data_entrada:
        eventos.append(
            {
                "data": momento(animal.data_entrada),
                "tipo": "entrada",
                "titulo": "Entrada no rebanho",
                "descricao": animal.get_origem_display(),
            }
        )
    if animal.data_saida:
        eventos.append(
            {
                "data": momento(animal.data_saida),
                "tipo": "saida",
                "titulo": animal.get_situacao_display(),
                "descricao": animal.motivo_saida or "Saída registrada",
            }
        )

    from apps.reproducao.models import Nascimento

    nascimento = Nascimento.objects.select_related("parto").filter(animal=animal).first()
    if nascimento:
        eventos.append(
            {
                "data": momento(nascimento.parto.data_hora),
                "tipo": "nascimento",
                "titulo": "Nascimento",
                "descricao": nascimento.get_situacao_display(),
            }
        )

    for cobertura in animal.coberturas.prefetch_related("historico"):
        eventos.append(
            {
                "data": momento(cobertura.data),
                "tipo": "cobertura",
                "titulo": "Cobertura",
                "descricao": str(cobertura),
            }
        )
        eventos.extend(
            {
                "data": momento(historico.criado_em),
                "tipo": "cancelamento",
                "titulo": "Cobertura cancelada",
                "descricao": historico.justificativa,
            }
            for historico in cobertura.historico.all()
            if historico.evento == "CANCELAMENTO"
        )
    eventos.extend(
        {
            "data": momento(registro.data),
            "tipo": "diagnostico",
            "titulo": "Diagnóstico de gestação",
            "descricao": str(registro),
        }
        for registro in animal.diagnosticos_gestacao.all()
    )
    eventos.extend(
        {
            "data": momento(registro.data),
            "tipo": "perda_gestacional",
            "titulo": "Perda gestacional",
            "descricao": str(registro),
        }
        for registro in animal.perdas_gestacionais.all()
    )
    for parto in animal.partos.prefetch_related("historico"):
        eventos.append(
            {
                "data": momento(parto.data_hora),
                "tipo": "parto",
                "titulo": "Parto",
                "descricao": str(parto),
            }
        )
        eventos.extend(
            {
                "data": momento(historico.criado_em),
                "tipo": "cancelamento",
                "titulo": "Parto cancelado",
                "descricao": historico.justificativa,
            }
            for historico in parto.historico.all()
            if historico.evento == "CANCELAMENTO"
        )
    for lactacao in animal.lactacoes.all():
        eventos.append(
            {
                "data": momento(lactacao.data_inicio),
                "tipo": "lactacao",
                "titulo": "Início da lactação",
                "descricao": str(lactacao),
            }
        )
        if lactacao.data_secagem:
            eventos.append(
                {
                    "data": momento(lactacao.data_secagem),
                    "tipo": "lactacao",
                    "titulo": "Secagem",
                    "descricao": str(lactacao),
                }
            )
        if lactacao.data_encerramento:
            eventos.append(
                {
                    "data": momento(lactacao.data_encerramento),
                    "tipo": "lactacao",
                    "titulo": "Lactação encerrada",
                    "descricao": str(lactacao),
                }
            )
        if lactacao.situacao == lactacao.Situacao.CANCELADA:
            eventos.append(
                {
                    "data": momento(lactacao.atualizado_em),
                    "tipo": "cancelamento",
                    "titulo": "Lactação cancelada",
                    "descricao": lactacao.motivo_cancelamento,
                }
            )

    eventos.extend(
        {
            "data": momento(producao.ordenha.data),
            "tipo": "ordenha",
            "titulo": "Ordenha",
            "descricao": f"{producao.quantidade_litros} L — {producao.ordenha}",
        }
        for producao in animal.producoes_leite.select_related("ordenha").filter(
            ordenha__ativo_registro=True
        )
    )
    eventos.extend(
        {
            "data": momento(tratamento.data_hora),
            "tipo": "saude",
            "titulo": (
                "Tratamento cancelado"
                if tratamento.situacao == tratamento.Situacao.CANCELADO
                else tratamento.produto.get_tipo_display()
            ),
            "descricao": str(tratamento),
        }
        for tratamento in animal.tratamentos.select_related("produto").all()
    )
    eventos.extend(
        {
            "data": momento(historico.criado_em),
            "tipo": "parentesco",
            "titulo": "Filiação corrigida",
            "descricao": historico.justificativa,
        }
        for historico in animal.historico_parentesco.all()
    )
    if tipo:
        eventos = [evento for evento in eventos if evento["tipo"] == tipo]

    def data_evento(evento: dict[str, Any]) -> date:
        return timezone.localtime(evento["data"]).date()

    if inicio:
        eventos = [evento for evento in eventos if data_evento(evento) >= inicio]
    if fim:
        eventos = [evento for evento in eventos if data_evento(evento) <= fim]
    return sorted(eventos, key=lambda evento: evento["data"], reverse=True)
