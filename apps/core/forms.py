from django import forms

from .models import ConfiguracaoSistema


class ConfiguracaoSistemaForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoSistema
        fields = (
            "nome_propriedade",
            "gestacao_dias",
            "margem_parto_dias",
            "dias_diagnostico",
            "dias_secagem",
            "dias_sem_ordenha_alerta",
            "antecedencia_alerta_secagem_dias",
            "idade_bezerro_meses",
            "idade_novilha_meses",
            "queda_producao_percentual",
            "tolerancia_divergencia_litros",
            "tolerancia_divergencia_percentual",
            "tolerancia_financeira",
            "casas_decimais_litros",
            "casas_decimais_peso",
        )
        widgets = {
            "queda_producao_percentual": forms.NumberInput(attrs={"step": "0.01"}),
            "tolerancia_divergencia_litros": forms.NumberInput(attrs={"step": "0.001"}),
            "tolerancia_divergencia_percentual": forms.NumberInput(attrs={"step": "0.01"}),
            "tolerancia_financeira": forms.NumberInput(attrs={"step": "0.01"}),
        }
