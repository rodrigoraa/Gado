from __future__ import annotations

from calendar import monthrange
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from apps.relatorios.services import gerar_xlsx


class Command(BaseCommand):
    help = "Gera uma planilha mensal de produção e entregas."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competencia", help="Mês no formato AAAA-MM")
        parser.add_argument(
            "--saida",
            help="Diretório de saída (padrão: MEDIA_ROOT/relatorios_gerados)",
        )

    def handle(self, *args: object, **options: object) -> None:
        from django.utils import timezone

        from apps.financeiro.models import EntregaLeite
        from apps.leite.models import Ordenha

        texto = options.get("competencia") or timezone.localdate().strftime("%Y-%m")
        try:
            ano, mes = map(int, str(texto).split("-"))
            inicio = date(ano, mes, 1)
        except (TypeError, ValueError) as exc:
            raise CommandError("Use --competencia no formato AAAA-MM.") from exc
        fim = date(ano, mes, monthrange(ano, mes)[1])
        producao = (
            Ordenha.objects.filter(data__range=(inicio, fim))
            .exclude(situacao=Ordenha.Situacao.CANCELADA)
            .aggregate(total=Sum("quantidade_total"))["total"]
            or 0
        )
        entregas = (
            EntregaLeite.objects.filter(data_coleta__date__range=(inicio, fim))
            .exclude(situacao=EntregaLeite.Situacao.CANCELADA)
            .aggregate(litros=Sum("quantidade_litros"), liquido=Sum("valor_liquido"))
        )
        linhas = [
            ("Produção", producao, "litros"),
            ("Entregue", entregas["litros"] or 0, "litros"),
            ("Valor líquido", entregas["liquido"] or 0, "reais"),
        ]
        conteudo = gerar_xlsx(
            f"Resumo {mes:02d}-{ano}",
            ("Indicador", "Valor", "Unidade"),
            linhas,
        )
        saida = options.get("saida")
        diretorio = (
            Path(str(saida)).resolve()
            if saida
            else (Path(settings.MEDIA_ROOT) / "relatorios_gerados").resolve()
        )
        diretorio.mkdir(parents=True, exist_ok=True)
        arquivo = diretorio / f"relatorio-mensal-{ano}-{mes:02d}.xlsx"
        if arquivo.exists():
            raise CommandError(f"O arquivo já existe: {arquivo}")
        arquivo.write_bytes(conteudo)
        self.stdout.write(self.style.SUCCESS(f"Relatório criado em {arquivo}"))
