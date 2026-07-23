from django import template

register = template.Library()


@register.filter
def item(lista: object, indice: int) -> object:
    try:
        return lista[indice]  # type: ignore[index]
    except (IndexError, KeyError, TypeError):
        return ""
