from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Cria um conjunto idempotente de dados de demonstração."

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        from apps.core.alertas import verificar_todos
        from apps.core.models import ConfiguracaoSistema
        from apps.financeiro.models import (
            EntregaLeite,
            FechamentoLeite,
            Laticinio,
            PrecoLeite,
            RecebimentoLeite,
        )
        from apps.financeiro.services import (
            criar_fechamento,
            registrar_recebimento,
            salvar_entrega,
            salvar_laticinio,
            salvar_preco,
        )
        from apps.lactacao.models import Lactacao
        from apps.leite.models import DestinoLeite, Ordenha
        from apps.leite.services import registrar_ordenha_com_producoes, salvar_destino
        from apps.rebanho.models import Animal, Lote, Pesagem, Raca
        from apps.rebanho.services import registrar_pesagem, salvar_animal, salvar_lote, salvar_raca
        from apps.reproducao.models import Cobertura, DiagnosticoGestacao, Parto
        from apps.reproducao.services import (
            registrar_cobertura,
            registrar_diagnostico,
            registrar_parto,
        )
        from apps.saude.models import ProdutoSaude, Tratamento
        from apps.saude.services import salvar_produto, salvar_tratamento

        hoje = timezone.localdate()
        agora = timezone.now()
        config = ConfiguracaoSistema.obter()
        if config.nome_propriedade == "Minha propriedade":
            config.nome_propriedade = "Sítio Boa Esperança — Demonstração"
            config.save()

        raca = Raca.objects.filter(nome="Girolando").first()
        if not raca:
            raca = salvar_raca(
                nome="Girolando", descricao="Raça leiteira de demonstração", ativa=True
            )
        lote = Lote.objects.filter(nome="Lote Lactação").first()
        if not lote:
            lote = salvar_lote(nome="Lote Lactação", descricao="Pasto principal", ativo=True)

        def animal_demo(
            identificacao: str,
            nome: str,
            sexo: str,
            anos: int,
            *,
            mae: Animal | None = None,
            pai: Animal | None = None,
        ) -> Animal:
            animal = Animal.objects.filter(identificacao=identificacao).first()
            if animal:
                return animal
            nascimento = hoje.replace(year=hoje.year - anos)
            return salvar_animal(
                identificacao=identificacao,
                nome=nome,
                sexo=sexo,
                data_nascimento=nascimento,
                raca=raca,
                mae=mae,
                pai=pai,
                origem=Animal.Origem.NASCIDO_SITIO,
                data_entrada=nascimento,
                situacao=Animal.Situacao.ATIVO,
                lote=lote,
                observacoes="[DEMO] Registro criado pelo seed_demo.",
            )

        touro = animal_demo("T-001", "Trovão", Animal.Sexo.MACHO, 6)
        estrela = animal_demo("V-001", "Estrela", Animal.Sexo.FEMEA, 5)
        aurora = animal_demo("V-002", "Aurora", Animal.Sexo.FEMEA, 4)
        canela = animal_demo("V-003", "Canela", Animal.Sexo.FEMEA, 3)

        for indice, (animal, peso) in enumerate(
            ((estrela, "465.20"), (aurora, "438.70"), (touro, "718.40")), start=1
        ):
            if not Pesagem.objects.filter(animal=animal, observacoes__contains="[DEMO]").exists():
                registrar_pesagem(
                    animal=animal,
                    data_pesagem=hoje - timedelta(days=20 - indice),
                    peso_kg=Decimal(peso),
                    responsavel="Administrador",
                    observacoes="[DEMO] Pesagem inicial.",
                )

        parto = Parto.objects.filter(vaca=estrela, observacoes__contains="[DEMO]").first()
        if not parto:
            data_cobertura = hoje - timedelta(days=373)
            cobertura_parto = registrar_cobertura(
                vaca=estrela,
                touro=touro,
                data_cobertura=data_cobertura,
                tipo=Cobertura.Tipo.MONTA_NATURAL,
                forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
                observacoes="[DEMO] Cobertura histórica.",
            )
            registrar_diagnostico(
                cobertura=cobertura_parto,
                data_diagnostico=data_cobertura + timedelta(days=50),
                resultado=DiagnosticoGestacao.Resultado.PRENHE,
                metodo=DiagnosticoGestacao.Metodo.PALPACAO,
                responsavel="Veterinário demonstrativo",
                observacoes="[DEMO] Prenhez confirmada.",
            )
            data_parto = hoje - timedelta(days=90)
            parto = registrar_parto(
                vaca=estrela,
                cobertura=cobertura_parto,
                data_hora=timezone.make_aware(
                    datetime.combine(data_parto, time(5, 40)), timezone.get_current_timezone()
                ),
                resultado=Parto.Resultado.NORMAL,
                bezerros=[
                    {
                        "identificacao_provisoria": "BEZ-DEMO-01",
                        "nome": "Lua",
                        "sexo": Animal.Sexo.FEMEA,
                        "situacao": "VIVO",
                        "peso_ao_nascer_kg": Decimal("32.40"),
                        "raca": raca,
                        "observacoes": "[DEMO] Nascimento demonstrativo.",
                    }
                ],
                necessitou_auxilio=False,
                responsavel="Administrador",
                observacoes="[DEMO] Parto demonstrativo.",
                iniciar_lactacao_automaticamente=True,
            )

        if not Cobertura.objects.filter(vaca=aurora, observacoes__contains="[DEMO] Atual").exists():
            cobertura_atual = registrar_cobertura(
                vaca=aurora,
                touro=touro,
                data_cobertura=hoje - timedelta(days=90),
                tipo=Cobertura.Tipo.MONTA_NATURAL,
                forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
                observacoes="[DEMO] Atual — prenhez em acompanhamento.",
            )
            registrar_diagnostico(
                cobertura=cobertura_atual,
                data_diagnostico=hoje - timedelta(days=43),
                resultado=DiagnosticoGestacao.Resultado.PRENHE,
                metodo=DiagnosticoGestacao.Metodo.PALPACAO,
                responsavel="Veterinário demonstrativo",
                observacoes="[DEMO] Diagnóstico atual.",
            )

        lactacao = Lactacao.objects.filter(vaca=estrela, situacao=Lactacao.Situacao.ATIVA).first()
        if lactacao:
            for dias_atras in range(10, 0, -1):
                dia = hoje - timedelta(days=dias_atras)
                marcador = f"[DEMO] Ordenha D-{dias_atras}"
                if Ordenha.objects.filter(observacoes=marcador).exists():
                    continue
                litros = Decimal("18.000") + Decimal(10 - dias_atras) / Decimal("4")
                ordenha = registrar_ordenha_com_producoes(
                    dados_ordenha={
                        "data": dia,
                        "periodo": Ordenha.Periodo.MANHA,
                        "horario": time(6, 0),
                        "lote": lote,
                        "modo": Ordenha.Modo.INDIVIDUAL,
                        "quantidade_total": litros,
                        "quantidade_vacas": 1,
                        "responsavel": "Administrador",
                        "observacoes": marcador,
                    },
                    producoes=[{"vaca": estrela, "quantidade_litros": litros}],
                )
                salvar_destino(
                    data=dia,
                    ordenha=ordenha,
                    tipo=DestinoLeite.Tipo.LATICINIO,
                    quantidade_litros=(litros * Decimal("0.90")).quantize(Decimal("0.001")),
                    observacoes="[DEMO] Reservado para coleta.",
                )

        laticinio = Laticinio.objects.filter(razao_social="Laticínios Campo Verde Ltda.").first()
        if not laticinio:
            laticinio = salvar_laticinio(
                razao_social="Laticínios Campo Verde Ltda.",
                nome_fantasia="Campo Verde",
                codigo_produtor="DEMO-001",
                dia_fechamento=25,
                dia_pagamento=10,
                ativo=True,
                observacoes="[DEMO] Comprador demonstrativo.",
            )
        if not PrecoLeite.objects.filter(
            laticinio=laticinio, observacoes__contains="[DEMO]"
        ).exists():
            salvar_preco(
                laticinio=laticinio,
                data_inicial=hoje - timedelta(days=365),
                data_final=None,
                valor_litro=Decimal("2.4800"),
                observacoes="[DEMO] Preço vigente.",
            )
        entrega = EntregaLeite.objects.filter(numero_documento="DEMO-ROM-001").first()
        if not entrega:
            entrega = salvar_entrega(
                data_coleta=agora - timedelta(days=5),
                quantidade_litros=Decimal("160.000"),
                bonificacao_qualidade=Decimal("12.00"),
                numero_documento="DEMO-ROM-001",
                observacoes="[DEMO] Coleta demonstrativa.",
            )
        fechamento = FechamentoLeite.objects.filter(numero_demonstrativo="DEMO-FECH-001").first()
        if not fechamento:
            fechamento = criar_fechamento(
                entregas=[entrega],
                competencia=hoje.replace(day=1),
                data_inicial=hoje.replace(day=1),
                data_final=hoje,
                data_prevista_pagamento=hoje + timedelta(days=10),
                numero_demonstrativo="DEMO-FECH-001",
                observacoes="[DEMO] Fechamento demonstrativo.",
            )
        if not RecebimentoLeite.objects.filter(referencia="DEMO-PAG-001").exists():
            registrar_recebimento(
                fechamento=fechamento,
                data=hoje,
                valor=(fechamento.valor_liquido_calculado / Decimal("2")).quantize(Decimal("0.01")),
                forma_pagamento=RecebimentoLeite.FormaPagamento.PIX,
                referencia="DEMO-PAG-001",
                observacoes="[DEMO] Pagamento parcial.",
            )

        produto = ProdutoSaude.objects.filter(nome="Antibiótico demonstrativo").first()
        if not produto:
            produto = salvar_produto(
                nome="Antibiótico demonstrativo",
                tipo=ProdutoSaude.Tipo.MEDICAMENTO,
                fabricante="Laboratório Exemplo",
                unidade="mL",
                carencia_padrao_dias=3,
                observacoes="[DEMO] Sempre seguir bula e orientação veterinária.",
                ativo=True,
            )
        if not Tratamento.objects.filter(animal=canela, observacoes__contains="[DEMO]").exists():
            salvar_tratamento(
                animal=canela,
                produto=produto,
                data_hora=agora - timedelta(hours=12),
                dose=Decimal("10.000"),
                responsavel="Administrador",
                motivo="Tratamento demonstrativo",
                observacoes="[DEMO] Registro de carência.",
            )

        resultados = verificar_todos()
        self.stdout.write(
            self.style.SUCCESS(
                "Dados de demonstração prontos. O comando pode ser executado novamente "
                "sem duplicar "
                f"os registros marcados. Alertas: {sum(resultados.values())}."
            )
        )
