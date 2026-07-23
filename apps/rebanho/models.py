from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import ConfiguracaoSistema, TimeStampedUUIDModel
from apps.core.validators import validar_upload_imagem

if TYPE_CHECKING:
    from uuid import UUID


def foto_animal_upload_to(instance: Animal, filename: str) -> str:
    """Mantém nomes externos fora do caminho e distribui fotos por animal."""

    extensao = Path(filename).suffix.lower()
    return f"animais/{instance.pk}/foto{extensao}"


class ExclusaoFisicaProtegidaMixin(models.Model):
    """Registros zootécnicos são inativados/cancelados, nunca apagados na UI."""

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):  # type: ignore[no-untyped-def]
        raise ValidationError(
            _("Este registro possui histórico e não pode ser excluído fisicamente.")
        )


class Raca(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    nome = models.CharField(_("nome"), max_length=100)
    descricao = models.TextField(_("descrição"), blank=True)
    ativa = models.BooleanField(_("ativa"), default=True)

    class Meta:
        verbose_name = _("raça")
        verbose_name_plural = _("raças")
        ordering = ("nome",)
        constraints = [models.UniqueConstraint(Lower("nome"), name="rebanho_raca_nome_ci_unico")]

    def __str__(self) -> str:
        return self.nome


class Lote(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    nome = models.CharField(_("nome"), max_length=100)
    descricao = models.TextField(_("descrição"), blank=True)
    ativo = models.BooleanField(_("ativo"), default=True)

    class Meta:
        verbose_name = _("lote/pasto")
        verbose_name_plural = _("lotes/pastos")
        ordering = ("nome",)
        constraints = [models.UniqueConstraint(Lower("nome"), name="rebanho_lote_nome_ci_unico")]

    def __str__(self) -> str:
        return self.nome


class Animal(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    class Sexo(models.TextChoices):
        MACHO = "M", _("Macho")
        FEMEA = "F", _("Fêmea")

    class Origem(models.TextChoices):
        NASCIDO_SITIO = "NASCIDO_SITIO", _("Nascido no sítio")
        COMPRADO = "COMPRADO", _("Comprado")
        RECEBIDO = "RECEBIDO", _("Recebido")
        OUTRO = "OUTRO", _("Outro")

    class Situacao(models.TextChoices):
        ATIVO = "ATIVO", _("Ativo")
        VENDIDO = "VENDIDO", _("Vendido")
        MORTO = "MORTO", _("Morto")
        DESCARTADO = "DESCARTADO", _("Descartado")
        DESAPARECIDO = "DESAPARECIDO", _("Desaparecido")

    identificacao = models.CharField(
        _("identificação/brinco"), max_length=50, null=True, blank=True, unique=True
    )
    identificacao_provisoria = models.CharField(
        _("identificação provisória"),
        max_length=50,
        null=True,
        blank=True,
        unique=True,
    )
    nome = models.CharField(_("nome"), max_length=100, blank=True)
    cor = models.CharField(_("cor"), max_length=80, blank=True)
    sexo = models.CharField(_("sexo"), max_length=1, choices=Sexo.choices, blank=True, default="")
    data_nascimento = models.DateField(_("data de nascimento"), null=True, blank=True)
    data_nascimento_aproximada = models.BooleanField(
        _("data de nascimento aproximada"), default=False
    )
    raca = models.ForeignKey(
        Raca,
        verbose_name=_("raça"),
        on_delete=models.PROTECT,
        related_name="animais",
        null=True,
        blank=True,
    )
    mae = models.ForeignKey(
        "self",
        verbose_name=_("mãe"),
        on_delete=models.PROTECT,
        related_name="filhos_como_mae",
        null=True,
        blank=True,
    )
    pai = models.ForeignKey(
        "self",
        verbose_name=_("pai"),
        on_delete=models.PROTECT,
        related_name="filhos_como_pai",
        null=True,
        blank=True,
    )
    origem = models.CharField(
        _("origem"),
        max_length=20,
        choices=Origem.choices,
        default=Origem.NASCIDO_SITIO,
    )
    data_entrada = models.DateField(_("data de entrada"), null=True, blank=True)
    situacao = models.CharField(
        _("situação"),
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.ATIVO,
    )
    data_saida = models.DateField(_("data de saída"), null=True, blank=True)
    motivo_saida = models.CharField(_("motivo da saída"), max_length=255, blank=True)
    lote = models.ForeignKey(
        Lote,
        verbose_name=_("lote atual"),
        on_delete=models.PROTECT,
        related_name="animais",
        null=True,
        blank=True,
    )
    peso_atual = models.DecimalField(
        _("peso atual (kg)"),
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    foto = models.ImageField(
        _("foto"),
        upload_to=foto_animal_upload_to,
        null=True,
        blank=True,
        validators=[validar_upload_imagem],
    )
    observacoes = models.TextField(_("observações"), blank=True)

    class Meta:
        verbose_name = _("animal")
        verbose_name_plural = _("animais")
        ordering = ("identificacao", "identificacao_provisoria", "nome")
        indexes = [
            models.Index(fields=("situacao", "sexo"), name="rebanho_animal_sit_sexo_idx"),
            models.Index(fields=("data_nascimento",), name="rebanho_animal_nasc_idx"),
            models.Index(fields=("lote", "situacao"), name="rebanho_animal_lote_sit_idx"),
            models.Index(fields=("nome",), name="rebanho_animal_nome_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(peso_atual__isnull=True) | Q(peso_atual__gt=0),
                name="rebanho_animal_peso_positivo",
            ),
            models.CheckConstraint(condition=~Q(mae=F("id")), name="rebanho_animal_mae_nao_self"),
            models.CheckConstraint(condition=~Q(pai=F("id")), name="rebanho_animal_pai_nao_self"),
        ]

    def __str__(self) -> str:
        return self.nome or self.identificador_exibicao

    @property
    def identificador_exibicao(self) -> str:
        return self.nome or self.identificacao or self.identificacao_provisoria or str(self.pk)

    @property
    def esta_ativo(self) -> bool:
        return self.situacao == self.Situacao.ATIVO

    @property
    def idade_em_meses(self) -> int | None:
        if not self.data_nascimento:
            return None
        hoje = timezone.localdate()
        meses = (hoje.year - self.data_nascimento.year) * 12
        meses += hoje.month - self.data_nascimento.month
        if hoje.day < self.data_nascimento.day:
            meses -= 1
        return max(meses, 0)

    @property
    def idade_em_anos(self) -> int | None:
        meses = self.idade_em_meses
        return meses // 12 if meses is not None else None

    @property
    def idade(self) -> str:
        idade_em_meses = self.idade_em_meses
        if idade_em_meses is None:
            return _("Não informada")
        anos, meses = divmod(idade_em_meses, 12)
        partes: list[str] = []
        if anos:
            partes.append(f"{anos} ano{'s' if anos != 1 else ''}")
        if meses or not partes:
            partes.append(f"{meses} {'meses' if meses != 1 else 'mês'}")
        return " e ".join(partes)

    def _valor_configuracao(self, campo: str, padrao: int) -> int:
        try:
            configuracao = ConfiguracaoSistema.obter()
            return int(getattr(configuracao, campo, padrao))
        except Exception:
            return int(getattr(settings, campo.upper(), padrao))

    @property
    def categoria(self) -> str:
        if not self.esta_ativo:
            return _("Animal inativo")

        idade_em_meses = self.idade_em_meses
        if idade_em_meses is None:
            return _("Animal")
        limite_bezerro = self._valor_configuracao("idade_bezerro_meses", 12)
        if idade_em_meses < limite_bezerro:
            if self.sexo == self.Sexo.FEMEA:
                return _("Bezerra")
            return _("Bezerro")

        if self.sexo == self.Sexo.MACHO:
            if self.filhos_como_pai.exists():
                return _("Touro")
            return _("Boi")
        if self.sexo != self.Sexo.FEMEA:
            return _("Animal")

        try:
            tem_parto = self.partos.exclude(situacao="CANCELADO").exists()
        except (AttributeError, ValueError):
            tem_parto = False
        return _("Vaca") if tem_parto else _("Novilha")

    @property
    def filhos(self):  # type: ignore[no-untyped-def]
        return Animal.objects.filter(Q(mae=self) | Q(pai=self)).order_by("-data_nascimento")

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        hoje = timezone.localdate()

        self.identificacao = (self.identificacao or "").strip().upper() or None
        self.identificacao_provisoria = (
            self.identificacao_provisoria or ""
        ).strip().upper() or None
        identificadores = {
            valor for valor in (self.identificacao, self.identificacao_provisoria) if valor
        }
        if (
            self.identificacao
            and self.identificacao_provisoria
            and self.identificacao == self.identificacao_provisoria
        ):
            erros["identificacao_provisoria"] = _(
                "A identificação provisória deve ser diferente da definitiva."
            )
        if identificadores:
            colisoes = Animal.objects.exclude(pk=self.pk).filter(
                Q(identificacao__in=identificadores)
                | Q(identificacao_provisoria__in=identificadores)
            )
            if colisoes.exists():
                mensagem = _(
                    "Esta identificação já é usada, como definitiva ou provisória, "
                    "por outro animal."
                )
                erros["identificacao"] = mensagem
                if self.identificacao_provisoria:
                    erros["identificacao_provisoria"] = mensagem
        if self.data_nascimento and self.data_nascimento > hoje:
            erros["data_nascimento"] = _("A data de nascimento não pode ser futura.")
        if self.data_entrada and self.data_nascimento and self.data_entrada < self.data_nascimento:
            erros["data_entrada"] = _("A entrada não pode ocorrer antes do nascimento.")
        if self.data_entrada and self.data_entrada > hoje:
            erros["data_entrada"] = _("A data de entrada não pode ser futura.")
        if self.data_saida and self.data_nascimento and self.data_saida < self.data_nascimento:
            erros["data_saida"] = _("A saída não pode ocorrer antes do nascimento.")
        if self.data_saida and self.data_saida > hoje:
            erros["data_saida"] = _("A data de saída não pode ser futura.")
        if self.situacao != self.Situacao.ATIVO and not self.motivo_saida:
            erros["motivo_saida"] = _("Informe o motivo ao marcar o animal como inativo.")

        if self.mae_id:
            if self.mae_id == self.pk:
                erros["mae"] = _("Um animal não pode ser mãe de si mesmo.")
            elif self.mae.sexo != self.Sexo.FEMEA:
                erros["mae"] = _("A mãe deve ser uma fêmea.")
            elif self._ancestral_contem(self.mae, self.pk):
                erros["mae"] = _("Este vínculo criaria um ciclo de parentesco.")
        if self.pai_id:
            if self.pai_id == self.pk:
                erros["pai"] = _("Um animal não pode ser pai de si mesmo.")
            elif self.pai.sexo != self.Sexo.MACHO:
                erros["pai"] = _("O pai deve ser um macho.")
            elif self._ancestral_contem(self.pai, self.pk):
                erros["pai"] = _("Este vínculo criaria um ciclo de parentesco.")
        if erros:
            raise ValidationError(erros)

    @staticmethod
    def _ancestral_contem(candidato: Animal, animal_id: UUID) -> bool:
        """Percorre ascendentes e bloqueia ciclos diretos ou indiretos."""

        pendentes = [candidato]
        visitados: set[object] = set()
        while pendentes:
            atual = pendentes.pop()
            if atual.pk == animal_id:
                return True
            if atual.pk in visitados:
                continue
            visitados.add(atual.pk)
            ids = [pk for pk in (atual.mae_id, atual.pai_id) if pk]
            if ids:
                pendentes.extend(Animal.objects.filter(pk__in=ids).only("id", "mae", "pai"))
        return False


class MovimentacaoLote(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="movimentacoes_lote")
    lote_anterior = models.ForeignKey(
        Lote,
        on_delete=models.PROTECT,
        related_name="movimentacoes_saida",
        null=True,
        blank=True,
    )
    novo_lote = models.ForeignKey(
        Lote,
        on_delete=models.PROTECT,
        related_name="movimentacoes_entrada",
        null=True,
        blank=True,
    )
    data = models.DateField(_("data"), default=timezone.localdate)
    motivo = models.CharField(_("motivo"), max_length=255)
    observacoes = models.TextField(_("observações"), blank=True)

    class Meta:
        verbose_name = _("movimentação de lote")
        verbose_name_plural = _("movimentações de lote")
        ordering = ("-data", "-criado_em")
        indexes = [models.Index(fields=("animal", "-data"), name="rebanho_mov_animal_data_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(lote_anterior__isnull=True)
                    | Q(novo_lote__isnull=True)
                    | ~Q(lote_anterior=F("novo_lote"))
                ),
                name="rebanho_mov_lotes_diferentes",
            )
        ]

    def __str__(self) -> str:
        destino = self.novo_lote or _("Sem lote")
        return f"{self.animal} → {destino} ({self.data:%d/%m/%Y})"

    def clean(self) -> None:
        super().clean()
        erros: dict[str, str] = {}
        if self.data and self.data > timezone.localdate():
            erros["data"] = _("A data da movimentação não pode ser futura.")
        if self.lote_anterior_id == self.novo_lote_id:
            erros["novo_lote"] = _("Escolha um lote diferente do lote atual.")
        if self.novo_lote_id and not self.novo_lote.ativo:
            erros["novo_lote"] = _("Não é possível mover para um lote inativo.")
        if erros:
            raise ValidationError(erros)


class Pesagem(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="pesagens")
    data = models.DateField(_("data"), default=timezone.localdate)
    peso_kg = models.DecimalField(
        _("peso (kg)"),
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    responsavel = models.CharField(_("responsável"), max_length=150, blank=True)
    observacoes = models.TextField(_("observações"), blank=True)

    class Meta:
        verbose_name = _("pesagem")
        verbose_name_plural = _("pesagens")
        ordering = ("-data", "-criado_em")
        indexes = [models.Index(fields=("animal", "-data"), name="rebanho_pes_animal_data_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(peso_kg__gt=0), name="rebanho_pesagem_peso_positivo")
        ]

    def __str__(self) -> str:
        return f"{self.animal} — {self.peso_kg} kg em {self.data:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        if self.data and self.data > timezone.localdate():
            raise ValidationError({"data": _("A data da pesagem não pode ser futura.")})
        if (
            self.animal_id
            and self.animal.data_nascimento
            and self.data < self.animal.data_nascimento
        ):
            raise ValidationError({"data": _("A pesagem não pode ocorrer antes do nascimento.")})

    @property
    def pesagem_anterior(self) -> Pesagem | None:
        if not self.animal_id:
            return None
        return (
            Pesagem.objects.filter(animal_id=self.animal_id)
            .filter(Q(data__lt=self.data) | Q(data=self.data, criado_em__lt=self.criado_em))
            .order_by("-data", "-criado_em")
            .first()
        )

    @property
    def diferenca_anterior(self) -> Decimal | None:
        anterior = self.pesagem_anterior
        return self.peso_kg - anterior.peso_kg if anterior else None

    @property
    def ganho_medio_diario(self) -> Decimal | None:
        anterior = self.pesagem_anterior
        if not anterior:
            return None
        dias = (self.data - anterior.data).days
        if dias <= 0:
            return None
        return (self.peso_kg - anterior.peso_kg) / Decimal(dias)


class HistoricoParentesco(ExclusaoFisicaProtegidaMixin, TimeStampedUUIDModel):
    """Preserva a linhagem anterior quando uma correção justificada é feita."""

    animal = models.ForeignKey(
        Animal, on_delete=models.PROTECT, related_name="historico_parentesco"
    )
    mae_anterior = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="historicos_como_mae_anterior",
        null=True,
        blank=True,
    )
    mae_nova = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="historicos_como_mae_nova",
        null=True,
        blank=True,
    )
    pai_anterior = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="historicos_como_pai_anterior",
        null=True,
        blank=True,
    )
    pai_novo = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="historicos_como_pai_novo",
        null=True,
        blank=True,
    )
    justificativa = models.TextField(_("justificativa"))

    class Meta:
        verbose_name = _("histórico de parentesco")
        verbose_name_plural = _("históricos de parentesco")
        ordering = ("-criado_em",)
        indexes = [
            models.Index(fields=("animal", "-criado_em"), name="rebanho_hist_parent_animal_idx")
        ]

    def __str__(self) -> str:
        return f"Correção de parentesco de {self.animal}"
