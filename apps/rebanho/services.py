from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Min, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.uploads import (
    capturar_dados_upload,
    desativar_metadados_upload,
    registrar_metadados_upload,
)

from .models import (
    Animal,
    HistoricoParentesco,
    Lote,
    MovimentacaoLote,
    Pesagem,
    Raca,
)

REGISTRO_AUTOMATICO = "Alteração registrada automaticamente pelo sistema."


def _validar_salvar(instancia: Any, *, update_fields: list[str] | None = None) -> Any:
    instancia.full_clean()
    instancia.save(update_fields=update_fields)
    return instancia


def _como_data(valor: date | datetime | None) -> date | None:
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            return timezone.localtime(valor).date()
        return valor.date()
    return valor


def _inferir_tipo_animal(dados: dict[str, Any]) -> str:
    nascimento = _como_data(dados.get("data_nascimento"))
    if isinstance(nascimento, str):
        try:
            nascimento = date.fromisoformat(nascimento)
        except ValueError:
            nascimento = None
    if nascimento:
        hoje = timezone.localdate()
        meses = (hoje.year - nascimento.year) * 12 + hoje.month - nascimento.month
        if hoje.day < nascimento.day:
            meses -= 1
        if meses < 12:
            return Animal.TipoAnimal.BEZERRO
    if dados.get("sexo") == Animal.Sexo.MACHO:
        return Animal.TipoAnimal.BOI
    if dados.get("sexo") == Animal.Sexo.FEMEA:
        return Animal.TipoAnimal.NOVILHA
    return Animal.TipoAnimal.BEZERRO


def _primeira_data_dependente(animal: Animal) -> date | None:
    """Obtém o primeiro evento que passaria a anteceder um nascimento corrigido."""

    from apps.leite.models import ProducaoAnimal
    from apps.reproducao.models import Cobertura, DiagnosticoGestacao, Parto, PerdaGestacional

    valores = [
        animal.movimentacoes_lote.aggregate(valor=Min("data"))["valor"],
        animal.pesagens.aggregate(valor=Min("data"))["valor"],
        Animal.objects.filter(Q(mae=animal) | Q(pai=animal)).aggregate(
            valor=Min("data_nascimento")
        )["valor"],
        Cobertura.objects.filter(Q(vaca=animal) | Q(touro=animal)).aggregate(valor=Min("data"))[
            "valor"
        ],
        DiagnosticoGestacao.objects.filter(vaca=animal).aggregate(valor=Min("data"))["valor"],
        PerdaGestacional.objects.filter(vaca=animal).aggregate(valor=Min("data"))["valor"],
        Parto.objects.filter(vaca=animal).aggregate(valor=Min("data_hora"))["valor"],
        ProducaoAnimal.objects.filter(vaca=animal).aggregate(valor=Min("ordenha__data"))["valor"],
    ]
    datas = [data_convertida for valor in valores if (data_convertida := _como_data(valor))]
    if animal.data_entrada:
        datas.append(animal.data_entrada)
    if animal.data_saida:
        datas.append(animal.data_saida)
    return min(datas) if datas else None


def _validar_correcao_sexo(*, animal: Animal, novo_sexo: str) -> None:
    from apps.leite.models import ProducaoAnimal
    from apps.reproducao.models import Cobertura, DiagnosticoGestacao, Parto, PerdaGestacional

    if novo_sexo == Animal.Sexo.MACHO:
        possui_papel_incompativel = any(
            (
                Animal.objects.filter(mae=animal).exists(),
                Cobertura.objects.filter(vaca=animal).exists(),
                DiagnosticoGestacao.objects.filter(vaca=animal).exists(),
                PerdaGestacional.objects.filter(vaca=animal).exists(),
                Parto.objects.filter(vaca=animal).exists(),
                ProducaoAnimal.objects.filter(vaca=animal).exists(),
            )
        )
        mensagem = _("O sexo não pode ser alterado: o animal possui histórico como fêmea.")
    else:
        possui_papel_incompativel = any(
            (
                Animal.objects.filter(pai=animal).exists(),
                Cobertura.objects.filter(touro=animal).exists(),
            )
        )
        mensagem = _("O sexo não pode ser alterado: o animal possui histórico como macho.")
    if possui_papel_incompativel:
        raise ValidationError({"sexo": mensagem})


@transaction.atomic
def salvar_raca(*, raca: Raca | None = None, **dados: Any) -> Raca:
    if raca is None:
        raca = Raca(**dados)
    else:
        raca = Raca.objects.select_for_update().get(pk=raca.pk)
        for campo, valor in dados.items():
            setattr(raca, campo, valor)
    return _validar_salvar(raca)


@transaction.atomic
def salvar_lote(*, lote: Lote | None = None, **dados: Any) -> Lote:
    if lote is None:
        lote = Lote(**dados)
    else:
        lote = Lote.objects.select_for_update().get(pk=lote.pk)
        for campo, valor in dados.items():
            setattr(lote, campo, valor)
    return _validar_salvar(lote)


@transaction.atomic
def salvar_animal(
    *,
    animal: Animal | None = None,
    justificativa_parentesco: str = "",
    justificativa_correcao: str = "",
    **dados: Any,
) -> Animal:
    """Cria/corrige um animal e preserva toda troca de filiação."""

    foto_informada = "foto" in dados
    if foto_informada and dados.get("foto") is False:
        dados["foto"] = None
    dados_upload_foto = capturar_dados_upload(dados.get("foto")) if foto_informada else None
    if animal is None:
        dados.setdefault("tipo_animal", _inferir_tipo_animal(dados))
        animal = Animal(**dados)
        _validar_salvar(animal)
        if dados_upload_foto:
            registrar_metadados_upload(
                objeto=animal,
                campo="foto",
                arquivo_salvo=animal.foto,
                dados=dados_upload_foto,
            )
        data_evento = animal.data_entrada or timezone.localdate()
        if animal.lote_id:
            _validar_salvar(
                MovimentacaoLote(
                    animal=animal,
                    lote_anterior=None,
                    novo_lote=animal.lote,
                    data=data_evento,
                    motivo=str(_("Lote informado no cadastro inicial.")),
                )
            )
        if animal.peso_atual is not None:
            _validar_salvar(
                Pesagem(
                    animal=animal,
                    data=timezone.localdate(),
                    peso_kg=animal.peso_atual,
                    observacoes=str(_("Peso informado no cadastro inicial.")),
                )
            )
        return animal

    atual = Animal.objects.select_for_update().get(pk=animal.pk)
    foto_anterior_nome = atual.foto.name if atual.foto else ""
    foto_anterior_storage = atual.foto.storage if atual.foto else None
    mae_anterior_id = atual.mae_id
    pai_anterior_id = atual.pai_id
    sexo_anterior = atual.sexo
    nascimento_anterior = atual.data_nascimento
    lote_anterior_id = atual.lote_id
    peso_anterior = atual.peso_atual
    for campo, valor in dados.items():
        setattr(atual, campo, valor)

    if atual.lote_id != lote_anterior_id:
        raise ValidationError({"lote": _("Use a ação Mudar lote para preservar o histórico.")})
    if atual.peso_atual != peso_anterior:
        raise ValidationError(
            {"peso_atual": _("Use a ação Registrar pesagem para preservar a evolução.")}
        )

    sexo_mudou = atual.sexo != sexo_anterior
    nascimento_mudou = atual.data_nascimento != nascimento_anterior
    justificativa_correcao = justificativa_correcao.strip() or REGISTRO_AUTOMATICO
    if sexo_mudou:
        _validar_correcao_sexo(animal=atual, novo_sexo=atual.sexo)
    if nascimento_mudou:
        from apps.reproducao.models import Nascimento

        if Nascimento.objects.select_for_update().filter(animal=atual).exists():
            raise ValidationError(
                {
                    "data_nascimento": _(
                        "A data deste nascimento deve ser corrigida pelo parto relacionado."
                    )
                }
            )
        primeira_data = _primeira_data_dependente(atual)
        if primeira_data and atual.data_nascimento and atual.data_nascimento > primeira_data:
            raise ValidationError(
                {
                    "data_nascimento": _(
                        "A nova data ficaria depois de um evento já registrado em %(data)s."
                    )
                    % {"data": primeira_data.strftime("%d/%m/%Y")}
                }
            )

    parentesco_mudou = atual.mae_id != mae_anterior_id or atual.pai_id != pai_anterior_id
    justificativa_parentesco = justificativa_parentesco.strip() or REGISTRO_AUTOMATICO

    if sexo_mudou or nascimento_mudou:
        descricao = []
        if sexo_mudou:
            descricao.append(f"sexo {sexo_anterior} → {atual.sexo}")
        if nascimento_mudou:
            nascimento_anterior_texto = (
                nascimento_anterior.strftime("%d/%m/%Y") if nascimento_anterior else "não informado"
            )
            nascimento_atual_texto = (
                atual.data_nascimento.strftime("%d/%m/%Y")
                if atual.data_nascimento
                else "não informado"
            )
            descricao.append(f"nascimento {nascimento_anterior_texto} → {nascimento_atual_texto}")
        nota = f"Correção cadastral ({', '.join(descricao)}): {justificativa_correcao.strip()}"
        atual.observacoes = f"{atual.observacoes}\n{nota}".strip()
    _validar_salvar(atual)
    foto_atual_nome = atual.foto.name if atual.foto else ""
    if foto_anterior_nome and foto_anterior_storage and foto_anterior_nome != foto_atual_nome:
        transaction.on_commit(lambda: foto_anterior_storage.delete(foto_anterior_nome))
    if dados_upload_foto:
        registrar_metadados_upload(
            objeto=atual,
            campo="foto",
            arquivo_salvo=atual.foto,
            dados=dados_upload_foto,
        )
    elif foto_informada and not atual.foto:
        desativar_metadados_upload(objeto=atual, campo="foto")
    if parentesco_mudou:
        historico = HistoricoParentesco(
            animal=atual,
            mae_anterior_id=mae_anterior_id,
            mae_nova=atual.mae,
            pai_anterior_id=pai_anterior_id,
            pai_novo=atual.pai,
            justificativa=justificativa_parentesco.strip(),
        )
        _validar_salvar(historico)
    return atual


@transaction.atomic
def inativar_animal(
    *,
    animal: Animal,
    situacao: str,
    motivo: str = "",
    data_saida: date | None = None,
) -> Animal:
    from apps.reproducao.models import Cobertura

    animal = Animal.objects.select_for_update().get(pk=animal.pk)
    if not animal.esta_ativo:
        raise ValidationError({"situacao": _("Este animal já está inativo.")})
    if situacao == Animal.Situacao.ATIVO or situacao not in Animal.Situacao.values:
        raise ValidationError({"situacao": _("Selecione uma situação de saída válida.")})
    motivo = motivo.strip() or REGISTRO_AUTOMATICO
    cobertura_aberta = (
        Cobertura.objects.select_for_update()
        .filter(vaca=animal, situacao__in=Cobertura.SITUACOES_ABERTAS)
        .first()
    )
    if cobertura_aberta:
        raise ValidationError(
            {"situacao": _("Encerre ou cancele a cobertura aberta antes de inativar a vaca.")}
        )
    animal.situacao = situacao
    animal.data_saida = data_saida or timezone.localdate()
    animal.motivo_saida = motivo.strip()
    return _validar_salvar(animal)


@transaction.atomic
def excluir_animal(*, animal: Animal) -> int:
    """Exclui o animal sem excluir seus filhos."""

    from apps.reproducao.models import Cobertura, HistoricoCobertura

    animal = Animal.objects.select_for_update().get(pk=animal.pk)
    foto_nome = animal.foto.name if animal.foto else ""
    foto_storage = animal.foto.storage if animal.foto else None

    filhos_sem_mae = Animal.objects.select_for_update().filter(mae=animal).update(mae=None)
    Animal.objects.select_for_update().filter(pai=animal).update(pai=None)

    # A cobertura continua válida quando o boi é apagado; ele passa a ser desconhecido.
    Cobertura.objects.select_for_update().filter(touro=animal).update(touro=None)

    try:
        # Uma cobertura sem vaca não possui significado, então acompanha a exclusão da vaca.
        HistoricoCobertura.objects.filter(cobertura__vaca=animal).delete()
        Cobertura.objects.select_for_update().filter(vaca=animal).delete()
        Animal.objects.filter(pk=animal.pk).delete()
    except ProtectedError as erro:
        raise ValidationError(
            _("Este animal ainda possui registros antigos vinculados e não pôde ser excluído.")
        ) from erro

    if foto_nome and foto_storage:
        transaction.on_commit(lambda: foto_storage.delete(foto_nome))
    return filhos_sem_mae


@transaction.atomic
def reativar_animal(*, animal: Animal, justificativa: str = "") -> Animal:
    animal = Animal.objects.select_for_update().get(pk=animal.pk)
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    animal.situacao = Animal.Situacao.ATIVO
    animal.data_saida = None
    animal.motivo_saida = ""
    animal.observacoes = f"{animal.observacoes}\nReativação: {justificativa.strip()}".strip()
    return _validar_salvar(animal)


@transaction.atomic
def movimentar_animal(
    *,
    animal: Animal,
    novo_lote: Lote | None,
    data_movimentacao: date,
    motivo: str,
    observacoes: str = "",
) -> MovimentacaoLote:
    animal = Animal.objects.select_for_update(of=("self",)).select_related("lote").get(pk=animal.pk)
    if not animal.esta_ativo:
        raise ValidationError({"animal": _("Somente animais ativos podem mudar de lote.")})
    if novo_lote is not None:
        novo_lote = Lote.objects.select_for_update().get(pk=novo_lote.pk)
        if not novo_lote.ativo:
            raise ValidationError({"novo_lote": _("O lote de destino está inativo.")})

    ultima = animal.movimentacoes_lote.order_by("-data", "-criado_em").first()
    if ultima and data_movimentacao < ultima.data:
        raise ValidationError(
            {"data": _("A movimentação não pode anteceder a última movimentação.")}
        )
    if animal.lote_id == (novo_lote.pk if novo_lote else None):
        raise ValidationError({"novo_lote": _("O animal já está neste lote.")})

    movimentacao = MovimentacaoLote(
        animal=animal,
        lote_anterior=animal.lote,
        novo_lote=novo_lote,
        data=data_movimentacao,
        motivo=motivo.strip(),
        observacoes=observacoes.strip(),
    )
    _validar_salvar(movimentacao)
    animal.lote = novo_lote
    animal.save(update_fields=["lote", "atualizado_em"])
    return movimentacao


@transaction.atomic
def registrar_pesagem(
    *,
    animal: Animal,
    data_pesagem: date,
    peso_kg: Decimal,
    responsavel: str = "",
    observacoes: str = "",
) -> Pesagem:
    animal = Animal.objects.select_for_update().get(pk=animal.pk)
    pesagem = Pesagem(
        animal=animal,
        data=data_pesagem,
        peso_kg=peso_kg,
        responsavel=responsavel.strip(),
        observacoes=observacoes.strip(),
    )
    _validar_salvar(pesagem)

    mais_recente = animal.pesagens.order_by("-data", "-criado_em").first()
    if mais_recente and mais_recente.pk == pesagem.pk:
        animal.peso_atual = pesagem.peso_kg
        animal.save(update_fields=["peso_atual", "atualizado_em"])
    return pesagem


@transaction.atomic
def corrigir_pesagem(
    *,
    pesagem: Pesagem,
    peso_kg: Decimal,
    data_pesagem: date,
    justificativa: str = "",
) -> Pesagem:
    pesagem = Pesagem.objects.select_for_update().select_related("animal").get(pk=pesagem.pk)
    justificativa = justificativa.strip() or REGISTRO_AUTOMATICO
    pesagem.peso_kg = peso_kg
    pesagem.data = data_pesagem
    pesagem.observacoes = f"{pesagem.observacoes}\nCorreção: {justificativa.strip()}".strip()
    _validar_salvar(pesagem)
    ultima = pesagem.animal.pesagens.order_by("-data", "-criado_em").first()
    if ultima:
        pesagem.animal.peso_atual = ultima.peso_kg
        pesagem.animal.save(update_fields=["peso_atual", "atualizado_em"])
    return pesagem
