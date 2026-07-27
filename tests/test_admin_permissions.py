from types import SimpleNamespace

from django.contrib.admin import AdminSite
from django.test import RequestFactory

from apps.leite.admin import OrdenhaAdmin, ProducaoAnimalAdmin
from apps.leite.models import Ordenha, ProducaoAnimal
from apps.rebanho.admin import AnimalAdmin
from apps.rebanho.models import Animal
from apps.reproducao.admin import DiagnosticoGestacaoAdmin, PartoAdmin
from apps.reproducao.models import DiagnosticoGestacao, Parto


def _request():  # type: ignore[no-untyped-def]
    request = RequestFactory().get("/admin/")
    request.user = SimpleNamespace(has_perm=lambda _permissao: True)
    return request


def test_admins_com_efeitos_colaterais_sao_somente_leitura() -> None:
    site = AdminSite()
    request = _request()
    protegidos = (
        (DiagnosticoGestacaoAdmin, DiagnosticoGestacao),
        (PartoAdmin, Parto),
        (OrdenhaAdmin, Ordenha),
        (ProducaoAnimalAdmin, ProducaoAnimal),
    )

    for admin_class, model in protegidos:
        model_admin = admin_class(model, site)
        assert model_admin.has_view_permission(request)
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


def test_parentesco_fica_bloqueado_na_edicao() -> None:
    site = AdminSite()
    request = _request()

    animal_admin = AnimalAdmin(Animal, site)
    assert "mae" not in animal_admin.get_readonly_fields(request, None)
    assert "pai" not in animal_admin.get_readonly_fields(request, None)
    campos_animal = animal_admin.get_readonly_fields(request, Animal())
    assert {"mae", "pai"}.issubset(campos_animal)
