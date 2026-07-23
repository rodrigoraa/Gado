from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from .models import UltimaAtividade


class UltimaAtividadeMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.user.is_authenticated and request.method in {"GET", "POST"}:
            chave = "ultima_atividade_registrada"
            ultima = request.session.get(chave)
            agora = timezone.now()
            intervalo = agora.timestamp() - float(ultima) if ultima else None
            if intervalo is None or intervalo >= timedelta(minutes=5).total_seconds():
                UltimaAtividade.objects.update_or_create(
                    usuario=request.user,
                    defaults={"caminho": request.path[:255]},
                )
                request.session[chave] = agora.timestamp()
        return response
