from __future__ import annotations

from typing import Any

from django import forms
from django.db.models import Q

from apps.lactacao.models import Lactacao
from apps.rebanho.models import Animal

from .models import DestinoLeite, Ordenha, ProducaoAnimal
from .services import atualizar_producao, registrar_producao, salvar_destino, salvar_ordenha


class BootstrapFormMixin:
    def _aplicar_bootstrap(self) -> None:
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
            if isinstance(field, forms.DecimalField):
                field.widget.attrs.setdefault("inputmode", "decimal")


class OrdenhaForm(BootstrapFormMixin, forms.ModelForm):
    periodo = forms.ChoiceField(
        label="Turno",
        choices=(
            (Ordenha.Periodo.MANHA, "Matutino"),
            (Ordenha.Periodo.TARDE, "Vespertino"),
            (Ordenha.Periodo.OUTRO, "2 Turnos"),
        ),
    )

    class Meta:
        model = Ordenha
        fields = ("data", "periodo", "quantidade_total")
        labels = {"quantidade_total": "Leite tirado (litros)"}
        widgets = {"data": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance._state.adding:
            self.initial.setdefault("periodo", Ordenha.Periodo.OUTRO)
        self._aplicar_bootstrap()

    def save(self, commit: bool = True) -> Ordenha:
        del commit
        dados = dict(self.cleaned_data)
        if self.instance._state.adding:
            dados.update(
                {
                    "modo": Ordenha.Modo.TOTAL,
                    "quantidade_vacas": 0,
                }
            )
        else:
            dados["motivo_correcao"] = "Valor atualizado pelo formulário simplificado."
        self.instance = salvar_ordenha(
            instancia=None if self.instance._state.adding else self.instance,
            **dados,
        )
        return self.instance


class ProducaoAnimalForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProducaoAnimal
        fields = ("ordenha", "vaca", "quantidade_litros", "observacoes")
        widgets = {"observacoes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        criterio_vacas = Q(
            sexo=Animal.Sexo.FEMEA,
            situacao=Animal.Situacao.ATIVO,
            lactacoes__situacao=Lactacao.Situacao.ATIVA,
        )
        if self.instance.vaca_id:
            criterio_vacas |= Q(pk=self.instance.vaca_id)
        self.fields["vaca"].queryset = Animal.objects.filter(criterio_vacas).distinct()
        if not self.instance._state.adding:
            self.fields["ordenha"].disabled = True
            self.fields["vaca"].disabled = True

    def save(self, commit: bool = True) -> ProducaoAnimal:
        del commit
        if not self.instance._state.adding:
            self.instance = atualizar_producao(
                producao=self.instance,
                quantidade_litros=self.cleaned_data["quantidade_litros"],
                observacoes=self.cleaned_data.get("observacoes", ""),
            )
        else:
            self.instance = registrar_producao(
                ordenha=self.cleaned_data["ordenha"],
                vaca=self.cleaned_data["vaca"],
                quantidade_litros=self.cleaned_data["quantidade_litros"],
                observacoes=self.cleaned_data.get("observacoes", ""),
            )
        return self.instance


class DestinoLeiteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DestinoLeite
        fields = ("data", "ordenha", "tipo", "quantidade_litros", "observacoes")
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()

    def save(self, commit: bool = True) -> DestinoLeite:
        del commit
        self.instance = salvar_destino(
            instancia=None if self.instance._state.adding else self.instance,
            **self.cleaned_data,
        )
        return self.instance


class ConciliacaoOrdenhaForm(BootstrapFormMixin, forms.Form):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()


class CancelarOrdenhaForm(BootstrapFormMixin, forms.Form):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
