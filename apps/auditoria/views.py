from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import RegistroAuditoria


@login_required
def lista(request: HttpRequest) -> HttpResponse:
    registros = RegistroAuditoria.objects.select_related("usuario")
    modulo = request.GET.get("modulo", "").strip()
    operacao = request.GET.get("operacao", "").strip()
    busca = request.GET.get("q", "").strip()
    if modulo:
        registros = registros.filter(modulo=modulo)
    if operacao:
        registros = registros.filter(operacao=operacao)
    if busca:
        registros = registros.filter(identificador__icontains=busca)
    pagina = Paginator(registros, 30).get_page(request.GET.get("page"))
    return render(
        request,
        "auditoria/lista.html",
        {
            "pagina": pagina,
            "page_obj": pagina,
            "modulos": (
                "rebanho",
                "reproducao",
                "leite",
                "core",
            ),
        },
    )
