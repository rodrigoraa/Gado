from __future__ import annotations

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.rebanho.forms import BootstrapFormMixin
from apps.rebanho.models import Animal
from apps.reproducao.models import Parto

from .models import Lactacao


class LactacaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lactacao
        fields = ("vaca", "parto", "data_inicio", "observacoes")
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        parto = kwargs.pop("parto", None)
        super().__init__(*args, **kwargs)
        self.fields["vaca"].queryset = Animal.objects.filter(
            sexo=Animal.Sexo.FEMEA, situacao=Animal.Situacao.ATIVO
        ).exclude(lactacoes__situacao=Lactacao.Situacao.ATIVA)
        self.fields["parto"].queryset = (
            Parto.objects.exclude(situacao=Parto.Situacao.CANCELADO)
            .filter(lactacao__isnull=True)
            .select_related("vaca")
        )
        self.fields["parto"].required = True
        if parto is not None:
            self.fields["parto"].initial = parto
            self.fields["parto"].widget = forms.HiddenInput()
            self.fields["vaca"].initial = parto.vaca
            self.fields["vaca"].widget = forms.HiddenInput()

    def clean(self):  # type: ignore[no-untyped-def]
        dados = super().clean()
        parto = dados.get("parto")
        vaca = dados.get("vaca")
        if not parto:
            self.add_error("parto", _("Selecione o parto que iniciou esta lactação."))
        if parto and vaca and parto.vaca_id != vaca.pk:
            self.add_error("parto", _("O parto pertence a outra vaca."))
        return dados


class DataObservacaoForm(BootstrapFormMixin, forms.Form):
    data = forms.DateField(
        label=_("Data"),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    observacoes = forms.CharField(
        label=_("Observações"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class CancelarLactacaoForm(BootstrapFormMixin, forms.Form):
    justificativa = forms.CharField(
        label=_("Justificativa"), widget=forms.Textarea(attrs={"rows": 3})
    )
