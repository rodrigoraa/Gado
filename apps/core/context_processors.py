from django.http import HttpRequest

from .models import ConfiguracaoSistema


def configuracao_global(request: HttpRequest) -> dict[str, object]:
    if not request.user.is_authenticated:
        return {}
    try:
        return {"configuracao_global": ConfiguracaoSistema.obter()}
    except Exception:
        return {}
