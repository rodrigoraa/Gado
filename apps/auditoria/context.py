from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_request_atual: ContextVar[Any | None] = ContextVar("audit_request", default=None)
_anteriores: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "audit_old_values", default=None
)


def definir_request(request: Any) -> Token[Any | None]:
    return _request_atual.set(request)


def restaurar_request(token: Token[Any | None]) -> None:
    _request_atual.reset(token)


def obter_request() -> Any | None:
    return _request_atual.get()


def guardar_anterior(chave: str, dados: dict[str, Any]) -> None:
    atuais = dict(_anteriores.get() or {})
    atuais[chave] = dados
    _anteriores.set(atuais)


def retirar_anterior(chave: str) -> dict[str, Any]:
    atuais = dict(_anteriores.get() or {})
    dados = atuais.pop(chave, {})
    _anteriores.set(atuais)
    return dados
