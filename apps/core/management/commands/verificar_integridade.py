from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F, Q


class Command(BaseCommand):
    help = "Executa verificações adicionais de integridade entre os domínios."

    def handle(self, *args: object, **options: object) -> None:
        from apps.financeiro.models import EntregaLeite
        from apps.lactacao.models import Lactacao
        from apps.leite.models import ProducaoAnimal
        from apps.rebanho.models import Animal

        problemas: list[str] = []
        lactacoes_duplicadas = (
            Lactacao.objects.filter(situacao=Lactacao.Situacao.ATIVA)
            .values("vaca_id")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .count()
        )
        if lactacoes_duplicadas:
            problemas.append(f"{lactacoes_duplicadas} vaca(s) com mais de uma lactação ativa")
        parentesco_invalido = Animal.objects.filter(Q(mae=F("id")) | Q(pai=F("id"))).count()
        if parentesco_invalido:
            problemas.append(f"{parentesco_invalido} autorreferência(s) de parentesco")
        producoes_sem_lactacao = ProducaoAnimal.objects.filter(lactacao__isnull=True).count()
        if producoes_sem_lactacao:
            problemas.append(f"{producoes_sem_lactacao} produção(ões) sem lactação")
        entregas_inconsistentes = (
            EntregaLeite.objects.filter(
                valor_liquido__gt=F("valor_bruto") + F("total_bonificacoes")
            )
            .exclude(total_descontos=0)
            .count()
        )
        if entregas_inconsistentes:
            problemas.append(f"{entregas_inconsistentes} entrega(s) com totais inconsistentes")
        if problemas:
            for problema in problemas:
                self.stderr.write(self.style.ERROR(problema))
            raise CommandError("Foram encontrados problemas de integridade.")
        self.stdout.write(
            self.style.SUCCESS("Integridade verificada; nenhuma inconsistência encontrada.")
        )
