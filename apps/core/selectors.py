from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone


def dashboard_indicadores() -> dict[str, object]:
    """Retorna somente os números usados no fluxo rural essencial."""

    from apps.leite.models import Ordenha
    from apps.leite.selectors import resumo_mensal
    from apps.rebanho.models import Animal
    from apps.reproducao.models import Cobertura

    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    animais_ativos = Animal.objects.filter(situacao=Animal.Situacao.ATIVO)
    ordenhas_mes = Ordenha.objects.filter(
        data__gte=inicio_mes,
        ativo_registro=True,
    ).exclude(situacao=Ordenha.Situacao.CANCELADA)
    coberturas_abertas = Cobertura.objects.filter(situacao__in=Cobertura.SITUACOES_ABERTAS)
    resumo_leite = resumo_mensal(ano=hoje.year, mes=hoje.month)

    return {
        "rebanho": {
            "ativos": animais_ativos.count(),
            "femeas": animais_ativos.filter(sexo=Animal.Sexo.FEMEA).count(),
            "machos": animais_ativos.filter(sexo=Animal.Sexo.MACHO).count(),
            "bezerros": animais_ativos.filter(
                mae__isnull=False,
            ).count(),
        },
        "reproducao": {
            "coberturas_abertas": coberturas_abertas.count(),
            "proxima_previsao": coberturas_abertas.order_by("previsao_atual_parto")
            .values_list("previsao_atual_parto", flat=True)
            .first(),
        },
        "leite": {
            "hoje": ordenhas_mes.filter(data=hoje).aggregate(total=Sum("quantidade_total"))["total"]
            or Decimal("0"),
            "mes": ordenhas_mes.aggregate(total=Sum("quantidade_total"))["total"] or Decimal("0"),
            "media_diaria": resumo_leite["media_diaria"],
            "dias_registrados": ordenhas_mes.aggregate(total=Count("data", distinct=True))["total"]
            or 0,
        },
    }
