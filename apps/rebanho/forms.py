from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import Animal, Lote, MovimentacaoLote, Pesagem, Raca


class BootstrapFormMixin:
    """Aplica controles grandes sem exigir JavaScript, pensando no celular."""

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                classe = "form-check-input"
            else:
                classe = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            campo.widget.attrs["class"] = f"{campo.widget.attrs.get('class', '')} {classe}".strip()


class RacaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Raca
        fields = ("nome", "descricao", "ativa")
        widgets = {"descricao": forms.Textarea(attrs={"rows": 3})}


class LoteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lote
        fields = ("nome", "descricao", "ativo")
        widgets = {"descricao": forms.Textarea(attrs={"rows": 3})}


class AnimalForm(BootstrapFormMixin, forms.ModelForm):
    nome = forms.CharField(label=_("Nome"), max_length=100, required=True)

    class Meta:
        model = Animal
        fields = ("nome", "cor", "sexo", "tipo_animal", "mae")

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance._state.adding and not self.initial.get("sexo"):
            self.initial["sexo"] = Animal.Sexo.FEMEA
        self.fields["sexo"].required = True
        self.fields["tipo_animal"].required = True
        self.fields["mae"].required = False
        self.fields["mae"].label = _("Mãe (opcional)")
        self.fields["mae"].help_text = _("São exibidas somente as vacas ativas.")
        filtro_maes = Q(
            sexo=Animal.Sexo.FEMEA,
            tipo_animal=Animal.TipoAnimal.VACA,
            situacao=Animal.Situacao.ATIVO,
        )
        if self.instance.mae_id:
            filtro_maes |= Q(pk=self.instance.mae_id)
        maes = Animal.objects.filter(filtro_maes)
        if self.instance.pk:
            maes = maes.exclude(pk=self.instance.pk)
        self.fields["mae"].queryset = maes.order_by(
            "nome",
            "identificacao",
            "identificacao_provisoria",
        )
        self.order_fields(("nome", "cor", "sexo", "tipo_animal", "mae"))


class CadastroBezerroForm(AnimalForm):
    class Meta(AnimalForm.Meta):
        fields = AnimalForm.Meta.fields

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.fields["tipo_animal"].initial = Animal.TipoAnimal.BEZERRO
        self.fields["tipo_animal"].widget = forms.HiddenInput()
        self.fields["tipo_animal"].required = False
        self.fields["mae"].required = False
        self.fields["mae"].label = _("Mãe, se conhecida")

    def clean_tipo_animal(self) -> str:
        return Animal.TipoAnimal.BEZERRO


class CadastroNovilhaForm(AnimalForm):
    data_nascimento = forms.DateField(
        label=_("Data de nascimento"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta(AnimalForm.Meta):
        fields = (*AnimalForm.Meta.fields, "data_nascimento")

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.fields["sexo"].initial = Animal.Sexo.FEMEA
        self.fields["sexo"].widget = forms.HiddenInput()
        self.fields["tipo_animal"].initial = Animal.TipoAnimal.NOVILHA
        self.fields["tipo_animal"].widget = forms.HiddenInput()
        self.fields["tipo_animal"].required = False
        self.order_fields(("nome", "cor", "sexo", "tipo_animal", "data_nascimento"))

    def clean_sexo(self) -> str:
        return Animal.Sexo.FEMEA

    def clean_tipo_animal(self) -> str:
        return Animal.TipoAnimal.NOVILHA

    def clean_data_nascimento(self):  # type: ignore[no-untyped-def]
        data_nascimento = self.cleaned_data["data_nascimento"]
        if data_nascimento and data_nascimento > Animal.data_limite_bezerro():
            raise ValidationError(
                _("Pela data informada, este animal ainda pertence à categoria bezerra.")
            )
        return data_nascimento


class InativacaoAnimalForm(BootstrapFormMixin, forms.Form):
    situacao = forms.ChoiceField(
        label=_("Nova situação"),
        choices=[
            escolha for escolha in Animal.Situacao.choices if escolha[0] != Animal.Situacao.ATIVO
        ],
    )
    data_saida = forms.DateField(
        label=_("Data de saída"), widget=forms.DateInput(attrs={"type": "date"})
    )


class MovimentacaoLoteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MovimentacaoLote
        fields = ("animal", "novo_lote", "data", "motivo", "observacoes")
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        animal = kwargs.pop("animal", None)
        super().__init__(*args, **kwargs)
        self.fields["animal"].queryset = Animal.objects.filter(situacao=Animal.Situacao.ATIVO)
        self.fields["novo_lote"].queryset = Lote.objects.filter(ativo=True)
        self.fields["novo_lote"].required = False
        if animal is not None:
            self.fields["animal"].initial = animal
            self.fields["animal"].widget = forms.HiddenInput()


class PesagemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Pesagem
        fields = ("animal", "data", "peso_kg", "responsavel", "observacoes")
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "peso_kg": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        animal = kwargs.pop("animal", None)
        super().__init__(*args, **kwargs)
        self.fields["animal"].queryset = Animal.objects.filter(situacao=Animal.Situacao.ATIVO)
        if animal is not None:
            self.fields["animal"].initial = animal
            self.fields["animal"].widget = forms.HiddenInput()
