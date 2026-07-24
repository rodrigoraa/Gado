from __future__ import annotations

from typing import Any

from django import forms

from .models import EntregaLeite, FechamentoLeite, Laticinio, PrecoLeite, RecebimentoLeite
from .services import (
    atualizar_dados_informados,
    criar_fechamento,
    registrar_recebimento,
    salvar_entrega,
    salvar_laticinio,
    salvar_preco,
)


class BootstrapFormMixin:
    def _aplicar_bootstrap(self) -> None:
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
            if isinstance(field, forms.DecimalField):
                field.widget.attrs.setdefault("inputmode", "decimal")


class LaticinioForm(BootstrapFormMixin, forms.ModelForm):
    confirmar_troca = forms.BooleanField(
        label="Confirmo a troca do laticínio ativo",
        required=False,
        help_text="Necessário apenas quando já existir outro laticínio ativo.",
    )

    class Meta:
        model = Laticinio
        fields = (
            "razao_social",
            "nome_fantasia",
            "cpf_cnpj",
            "telefone",
            "email",
            "endereco",
            "codigo_produtor",
            "dia_fechamento",
            "dia_pagamento",
            "observacoes",
            "ativo",
        )
        widgets = {
            "endereco": forms.Textarea(attrs={"rows": 3}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()

    def save(self, commit: bool = True) -> Laticinio:
        del commit
        dados = dict(self.cleaned_data)
        confirmar = dados.pop("confirmar_troca", False)
        self.instance = salvar_laticinio(
            instancia=None if self.instance._state.adding else self.instance,
            confirmar_troca=confirmar,
            **dados,
        )
        return self.instance


class PrecoLeiteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PrecoLeite
        fields = (
            "laticinio",
            "data_inicial",
            "data_final",
            "valor_litro",
            "observacoes",
        )
        widgets = {
            "data_inicial": forms.DateInput(attrs={"type": "date"}),
            "data_final": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        if self.instance._state.adding:
            ativo = Laticinio.objects.filter(ativo=True).first()
            if ativo:
                self.initial.setdefault("laticinio", ativo)

    def save(self, commit: bool = True) -> PrecoLeite:
        del commit
        self.instance = salvar_preco(
            instancia=None if self.instance._state.adding else self.instance,
            **self.cleaned_data,
        )
        return self.instance


class EntregaLeiteForm(BootstrapFormMixin, forms.ModelForm):
    valor_litro_manual = forms.DecimalField(
        label="Valor por litro (opcional)",
        required=False,
        max_digits=10,
        decimal_places=4,
        min_value=0,
        help_text="Deixe vazio para aplicar automaticamente o preço vigente.",
    )

    class Meta:
        model = EntregaLeite
        fields = (
            "data_coleta",
            "quantidade_litros",
            "bonificacao_qualidade",
            "bonificacao_volume",
            "outras_bonificacoes",
            "desconto_qualidade",
            "frete",
            "taxas",
            "outros_descontos",
            "data_prevista_pagamento",
            "numero_documento",
            "anexo",
            "observacoes",
        )
        widgets = {
            "data_coleta": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "data_prevista_pagamento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        self.fields["data_coleta"].input_formats = ("%Y-%m-%dT%H:%M",)
        if not self.instance._state.adding:
            self.initial["valor_litro_manual"] = self.instance.valor_litro

    def save(self, commit: bool = True) -> EntregaLeite:
        del commit
        dados = dict(self.cleaned_data)
        dados["valor_litro"] = dados.pop("valor_litro_manual", None)
        if not dados.get("data_prevista_pagamento"):
            dados.pop("data_prevista_pagamento", None)
        self.instance = salvar_entrega(
            instancia=None if self.instance._state.adding else self.instance,
            **dados,
        )
        return self.instance


class FechamentoLeiteForm(BootstrapFormMixin, forms.ModelForm):
    finalizar = forms.BooleanField(label="Finalizar fechamento agora", required=False, initial=True)

    class Meta:
        model = FechamentoLeite
        fields = (
            "competencia",
            "data_inicial",
            "data_final",
            "entregas",
            "total_litros_informado",
            "valor_bruto_informado",
            "bonificacoes_informadas",
            "descontos_informados",
            "valor_liquido_informado",
            "data_prevista_pagamento",
            "numero_demonstrativo",
            "arquivo_demonstrativo",
            "observacoes",
        )
        widgets = {
            "competencia": forms.DateInput(attrs={"type": "date"}),
            "data_inicial": forms.DateInput(attrs={"type": "date"}),
            "data_final": forms.DateInput(attrs={"type": "date"}),
            "data_prevista_pagamento": forms.DateInput(attrs={"type": "date"}),
            "entregas": forms.CheckboxSelectMultiple,
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        self.fields["entregas"].queryset = (
            EntregaLeite.objects.filter(
                ativo_registro=True,
                situacao__in=(
                    EntregaLeite.Situacao.REGISTRADA,
                    EntregaLeite.Situacao.AGUARDANDO_FECHAMENTO,
                ),
            )
            .select_related("laticinio")
            .order_by("data_coleta")
        )

    def save(self, commit: bool = True) -> FechamentoLeite:
        del commit
        dados = dict(self.cleaned_data)
        entregas = dados.pop("entregas")
        finalizar = dados.pop("finalizar", True)
        self.instance = criar_fechamento(entregas=entregas, finalizar=finalizar, **dados)
        return self.instance


class AjusteFechamentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = FechamentoLeite
        fields = (
            "total_litros_informado",
            "valor_bruto_informado",
            "bonificacoes_informadas",
            "descontos_informados",
            "valor_liquido_informado",
            "numero_demonstrativo",
            "arquivo_demonstrativo",
            "observacoes",
        )
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()

    def save(self, commit: bool = True) -> FechamentoLeite:
        del commit
        self.instance = atualizar_dados_informados(fechamento=self.instance, **self.cleaned_data)
        return self.instance


class RecebimentoLeiteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RecebimentoLeite
        fields = (
            "fechamento",
            "data",
            "valor",
            "forma_pagamento",
            "referencia",
            "anexo",
            "observacoes",
        )
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
        self.fields["fechamento"].queryset = FechamentoLeite.objects.filter(
            ativo_registro=True
        ).exclude(
            situacao__in=(
                FechamentoLeite.Situacao.ABERTO,
                FechamentoLeite.Situacao.PAGO,
                FechamentoLeite.Situacao.CANCELADO,
            )
        )

    def save(self, commit: bool = True) -> RecebimentoLeite:
        del commit
        self.instance = registrar_recebimento(**self.cleaned_data)
        return self.instance


class CancelamentoForm(BootstrapFormMixin, forms.Form):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aplicar_bootstrap()
