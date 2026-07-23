from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from .models import EventoSaude, ProdutoSaude, Tratamento
from .services import salvar_evento_saude, salvar_produto, salvar_tratamento


class BootstrapFormMixin:
    def _aplicar_bootstrap(self) -> None:
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
            if isinstance(field, forms.DecimalField):
                field.widget.attrs.setdefault("inputmode", "decimal")


class ProdutoSaudeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProdutoSaude
        fields = (
            "nome",
            "tipo",
            "fabricante",
            "unidade",
            "carencia_padrao_dias",
            "carencia_padrao_horas",
            "observacoes",
            "ativo",
        )
        widgets = {"observacoes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()

    def save(self, commit: bool = True) -> ProdutoSaude:
        del commit
        self.instance = salvar_produto(
            instancia=None if self.instance._state.adding else self.instance,
            **self.cleaned_data,
        )
        return self.instance


class TratamentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Tratamento
        fields = (
            "animal",
            "produto",
            "data_hora",
            "dose",
            "unidade",
            "responsavel",
            "motivo",
            "carencia_dias",
            "carencia_horas",
            "observacoes",
            "motivo_correcao",
        )
        widgets = {
            "data_hora": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "motivo": forms.Textarea(attrs={"rows": 2}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "motivo_correcao": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        self.fields["data_hora"].input_formats = ("%Y-%m-%dT%H:%M",)
        self.fields["produto"].queryset = ProdutoSaude.objects.filter(
            ativo=True
        ) | ProdutoSaude.objects.filter(pk=getattr(self.instance, "produto_id", None))
        if self.instance._state.adding:
            self.fields.pop("motivo_correcao", None)

    def save(self, commit: bool = True) -> Tratamento:
        del commit
        self.instance = salvar_tratamento(
            instancia=None if self.instance._state.adding else self.instance,
            **self.cleaned_data,
        )
        return self.instance


class CancelamentoForm(BootstrapFormMixin, forms.Form):
    motivo = forms.CharField(
        label="Motivo do cancelamento", widget=forms.Textarea(attrs={"rows": 3})
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()


class DescarteLeiteForm(BootstrapFormMixin, forms.Form):
    quantidade_litros = forms.DecimalField(
        label="Quantidade descartada (L)",
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    data = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}))
    observacoes = forms.CharField(
        label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()


class EventoSaudeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = EventoSaude
        fields = (
            "animal",
            "tipo",
            "data_hora",
            "titulo",
            "descricao",
            "veterinario",
            "responsavel",
            "resultado",
            "motivo_correcao",
        )
        widgets = {
            "data_hora": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "resultado": forms.Textarea(attrs={"rows": 3}),
            "motivo_correcao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        self.fields["data_hora"].input_formats = ("%Y-%m-%dT%H:%M",)
        if self.instance._state.adding:
            self.fields.pop("motivo_correcao", None)
        else:
            self.fields["motivo_correcao"].required = False
            self.fields[
                "motivo_correcao"
            ].help_text = "Obrigatória quando qualquer dado do evento for alterado."

    def save(self, commit: bool = True) -> EventoSaude:
        del commit
        self.instance = salvar_evento_saude(
            instancia=None if self.instance._state.adding else self.instance,
            **self.cleaned_data,
        )
        return self.instance
