from __future__ import annotations

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
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
    remover_foto = forms.BooleanField(
        label=_("Remover foto atual"),
        required=False,
    )

    class Meta:
        model = Animal
        fields = ("nome", "cor", "foto", "sexo")
        widgets = {"foto": forms.FileInput(attrs={"accept": "image/jpeg,image/png"})}

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance._state.adding and not self.initial.get("sexo"):
            self.initial["sexo"] = Animal.Sexo.FEMEA
        if self.instance._state.adding or not self.instance.foto:
            self.fields.pop("remover_foto", None)
        self.order_fields(("nome", "cor", "foto", "remover_foto", "sexo", "mae"))

    def clean(self):  # type: ignore[no-untyped-def]
        dados = super().clean()
        if dados.get("remover_foto"):
            if self.files.get("foto"):
                self.add_error(
                    "remover_foto",
                    _("Escolha entre enviar uma nova foto ou remover a foto atual."),
                )
            else:
                dados["foto"] = False
        return dados

    def clean_foto(self):  # type: ignore[no-untyped-def]
        arquivo = self.cleaned_data.get("foto")
        if not arquivo or not hasattr(arquivo, "size"):
            return arquivo
        limite = int(getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024))
        if arquivo.size > limite:
            raise ValidationError(_("A foto ultrapassa o limite permitido."))
        tipo = getattr(arquivo, "content_type", "")
        if tipo and tipo not in {"image/jpeg", "image/png"}:
            raise ValidationError(_("Envie uma imagem JPG, JPEG ou PNG válida."))
        return arquivo


class CadastroBezerroForm(AnimalForm):
    class Meta(AnimalForm.Meta):
        fields = (*AnimalForm.Meta.fields, "mae")

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.fields["mae"].required = False
        self.fields["mae"].label = _("Mãe, se conhecida")
        self.fields["mae"].queryset = Animal.objects.filter(
            sexo=Animal.Sexo.FEMEA,
            situacao=Animal.Situacao.ATIVO,
        ).order_by("nome")


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
        self.order_fields(
            ("nome", "cor", "foto", "remover_foto", "sexo", "data_nascimento")
        )

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
    motivo = forms.CharField(
        label=_("Motivo/justificativa"), widget=forms.Textarea(attrs={"rows": 3})
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
