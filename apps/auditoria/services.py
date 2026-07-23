from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from .models import RegistroAuditoria


def _ip_valido(valor: str | None) -> str | None:
    if not valor:
        return None
    primeiro = valor.split(",", maxsplit=1)[0].strip()
    return primeiro or None


def registrar_auditoria(
    *,
    modulo: str,
    entidade: str,
    identificador: object,
    operacao: str,
    dados_anteriores: dict[str, Any] | None = None,
    dados_novos: dict[str, Any] | None = None,
    justificativa: str = "",
    request: HttpRequest | None = None,
) -> RegistroAuditoria:
    meta = request.META if request else {}
    usuario = request.user if request and request.user.is_authenticated else None
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        ip=_ip_valido(meta.get("REMOTE_ADDR")),
        cf_connecting_ip=_ip_valido(meta.get("HTTP_CF_CONNECTING_IP")),
        x_forwarded_for=str(meta.get("HTTP_X_FORWARDED_FOR", ""))[:255],
        user_agent=str(meta.get("HTTP_USER_AGENT", ""))[:500],
        modulo=modulo,
        entidade=entidade,
        identificador=str(identificador),
        operacao=operacao,
        dados_anteriores=dados_anteriores or {},
        dados_novos=dados_novos or {},
        justificativa=justificativa,
    )
