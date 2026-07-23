from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .context import definir_request, restaurar_request


class AuditContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        token = definir_request(request)
        try:
            return self.get_response(request)
        finally:
            restaurar_request(token)
