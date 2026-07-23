from __future__ import annotations

import re

from django.core.exceptions import ValidationError

from apps.core.validators import validar_upload_privado


def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _cpf_valido(numero: str) -> bool:
    if len(numero) != 11 or numero == numero[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(numero[indice]) * (posicao + 1 - indice) for indice in range(posicao))
        digito = (soma * 10 % 11) % 10
        if digito != int(numero[posicao]):
            return False
    return True


def _cnpj_valido(numero: str) -> bool:
    if len(numero) != 14 or numero == numero[0] * 14:
        return False
    pesos = ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    base = numero[:12]
    for sequencia in pesos:
        resto = sum(int(digito) * peso for digito, peso in zip(base, sequencia, strict=True)) % 11
        base += str(0 if resto < 2 else 11 - resto)
    return base == numero


def validar_cpf_cnpj(valor: str) -> None:
    if not valor:
        return
    numero = _digitos(valor)
    if not (_cpf_valido(numero) or _cnpj_valido(numero)):
        raise ValidationError("Informe um CPF ou CNPJ válido.")


def validar_anexo(arquivo: object) -> None:
    if not arquivo:
        return
    validar_upload_privado(arquivo)
