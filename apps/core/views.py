from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import ConfiguracaoSistemaForm
from .models import Alerta, ConfiguracaoSistema
from .selectors import dashboard_indicadores


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "core/dashboard.html",
        {"indicadores": dashboard_indicadores()},
    )


@require_GET
def health_live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
def health_ready(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise RuntimeError("Há migrations pendentes.")
    except Exception:
        return JsonResponse({"status": "indisponível"}, status=503)
    return JsonResponse({"status": "ok"})


@login_required
def configuracoes(request: HttpRequest) -> HttpResponse:
    configuracao = ConfiguracaoSistema.obter()
    form = ConfiguracaoSistemaForm(request.POST or None, instance=configuracao)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configurações atualizadas.")
        return redirect("core:configuracoes")
    return render(
        request,
        "shared/form.html",
        {"form": form, "titulo": "Configurações da propriedade", "voltar_url": "/"},
    )


@login_required
def alertas(request: HttpRequest) -> HttpResponse:
    queryset = Alerta.objects.all()
    if request.GET.get("status") != "todos":
        queryset = queryset.filter(resolvido=False)
    return render(request, "core/alertas.html", {"alertas": queryset[:200]})


@login_required
@require_POST
def resolver_alerta(request: HttpRequest, pk: str) -> HttpResponse:
    try:
        alerta = Alerta.objects.get(pk=pk)
    except (Alerta.DoesNotExist, ValueError) as exc:
        raise Http404 from exc
    alerta.resolver(request.user)
    messages.success(request, "Alerta marcado como resolvido.")
    proximo = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        proximo,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        proximo = "core:alertas"
    return redirect(proximo)


@login_required
def arquivo_privado(request: HttpRequest, caminho: str) -> FileResponse:
    """Entrega anexos autenticados, bloqueando travessia de diretórios."""
    from django.conf import settings

    raiz = Path(settings.MEDIA_ROOT).resolve()
    alvo = (raiz / caminho).resolve()
    if raiz not in alvo.parents or not alvo.is_file():
        raise Http404
    response = FileResponse(alvo.open("rb"), as_attachment=request.GET.get("download") == "1")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def manipulador_erro_400(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "400.html", status=400)


def manipulador_erro_403(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "403.html", status=403)


def manipulador_erro_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "404.html", status=404)


def manipulador_erro_500(request: HttpRequest) -> HttpResponse:
    return render(request, "500.html", status=500)
