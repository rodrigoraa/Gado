from __future__ import annotations

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.rebanho.forms import BootstrapFormMixin
from apps.rebanho.models import Animal

from .models import Cobertura, DiagnosticoGestacao, Parto, PerdaGestacional


class CoberturaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Cobertura
        fields = ("vaca", "touro", "data")
        widgets = {"data": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        idade_adulta = Q(data_nascimento__isnull=True) | Q(
            data_nascimento__lte=Animal.data_limite_bezerro()
        )
        elegiveis = Animal.objects.filter(
            idade_adulta,
            situacao=Animal.Situacao.ATIVO,
        ).order_by("nome", "identificacao")
        self.fields["vaca"].queryset = elegiveis.filter(sexo=Animal.Sexo.FEMEA)
        self.fields["touro"].queryset = elegiveis.filter(sexo=Animal.Sexo.MACHO)
        self.fields["touro"].required = False
        self.fields["touro"].label = _("Boi adulto, se conhecido")
        if not self.is_bound and not self.initial.get("touro"):
            bois = list(self.fields["touro"].queryset.values_list("pk", flat=True)[:2])
            if len(bois) == 1:
                self.initial["touro"] = bois[0]


class AlterarDataCoberturaForm(BootstrapFormMixin, forms.Form):
    nova_data = forms.DateField(
        label=_("Nova data"), widget=forms.DateInput(attrs={"type": "date"})
    )
    justificativa = forms.CharField(
        label=_("Justificativa"), widget=forms.Textarea(attrs={"rows": 3})
    )


class JustificativaForm(BootstrapFormMixin, forms.Form):
    justificativa = forms.CharField(
        label=_("Justificativa"), widget=forms.Textarea(attrs={"rows": 3})
    )


class DiagnosticoGestacaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DiagnosticoGestacao
        fields = (
            "cobertura",
            "data",
            "resultado",
            "metodo",
            "responsavel",
            "idade_gestacional_estimada_dias",
            "nova_previsao_parto",
            "observacoes",
        )
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "nova_previsao_parto": forms.DateInput(attrs={"type": "date"}),
            "idade_gestacional_estimada_dias": forms.NumberInput(attrs={"min": "0"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        cobertura = kwargs.pop("cobertura", None)
        super().__init__(*args, **kwargs)
        self.fields["cobertura"].queryset = Cobertura.objects.filter(
            situacao__in=Cobertura.SITUACOES_ABERTAS
        ).select_related("vaca")
        if cobertura is not None:
            self.fields["cobertura"].initial = cobertura
            self.fields["cobertura"].widget = forms.HiddenInput()


class PerdaGestacionalForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PerdaGestacional
        fields = ("cobertura", "data", "tipo", "responsavel", "observacoes")
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        cobertura = kwargs.pop("cobertura", None)
        super().__init__(*args, **kwargs)
        self.fields["cobertura"].queryset = Cobertura.objects.filter(
            situacao__in=Cobertura.SITUACOES_ABERTAS
        ).select_related("vaca")
        if cobertura is not None:
            self.fields["cobertura"].initial = cobertura
            self.fields["cobertura"].widget = forms.HiddenInput()


class PartoForm(BootstrapFormMixin, forms.ModelForm):
    iniciar_lactacao = forms.BooleanField(
        label=_("Iniciar lactação para esta vaca"), required=False, initial=True
    )

    class Meta:
        model = Parto
        fields = (
            "vaca",
            "cobertura",
            "data_hora",
            "resultado",
            "necessitou_auxilio",
            "responsavel",
            "observacoes",
        )
        widgets = {
            "data_hora": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        cobertura = kwargs.pop("cobertura", None)
        super().__init__(*args, **kwargs)
        self.fields["data_hora"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["vaca"].queryset = Animal.objects.filter(
            sexo=Animal.Sexo.FEMEA, situacao=Animal.Situacao.ATIVO
        )
        self.fields["cobertura"].queryset = Cobertura.objects.filter(
            situacao__in=Cobertura.SITUACOES_ABERTAS
        ).select_related("vaca")
        self.fields["cobertura"].required = False
        if cobertura is not None:
            self.fields["cobertura"].initial = cobertura
            self.fields["cobertura"].widget = forms.HiddenInput()
            self.fields["vaca"].initial = cobertura.vaca
            self.fields["vaca"].widget = forms.HiddenInput()

    def clean(self):  # type: ignore[no-untyped-def]
        dados = super().clean()
        cobertura = dados.get("cobertura")
        vaca = dados.get("vaca")
        if cobertura and vaca and cobertura.vaca_id != vaca.pk:
            self.add_error("cobertura", _("A cobertura pertence a outra vaca."))
        return dados


class BezerroForm(BootstrapFormMixin, forms.Form):
    nome = forms.CharField(label=_("Nome"), max_length=100, required=True)
    cor = forms.CharField(label=_("Cor"), max_length=80, required=False)
    foto = forms.ImageField(label=_("Foto"), required=False)
    sexo = forms.ChoiceField(
        label=_("Sexo"),
        choices=(("", _("Não informado")), *Animal.Sexo.choices),
        required=False,
    )


BezerroFormSet = forms.formset_factory(
    BezerroForm,
    extra=1,
    can_delete=True,
    max_num=5,
    validate_max=True,
    absolute_max=5,
)


class CorrecaoPartoForm(BootstrapFormMixin, forms.ModelForm):
    justificativa = forms.CharField(
        label=_("Justificativa da correção"), widget=forms.Textarea(attrs={"rows": 3})
    )

    class Meta:
        model = Parto
        fields = (
            "data_hora",
            "resultado",
            "necessitou_auxilio",
            "responsavel",
            "observacoes",
        )
        widgets = {
            "data_hora": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.fields["data_hora"].input_formats = ["%Y-%m-%dT%H:%M"]
