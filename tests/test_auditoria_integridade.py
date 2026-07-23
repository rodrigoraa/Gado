from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.rebanho.models import Animal
from apps.rebanho.services import salvar_animal

pytestmark = pytest.mark.django_db


def test_falha_da_auditoria_reverte_operacao_atomica() -> None:
    with (
        patch(
            "apps.auditoria.signals.registrar_auditoria",
            side_effect=RuntimeError("auditoria indisponível"),
        ),
        pytest.raises(RuntimeError, match="auditoria indisponível"),
    ):
        salvar_animal(
            identificacao="AUD-ROLLBACK",
            sexo=Animal.Sexo.FEMEA,
            data_nascimento="2024-01-01",
        )

    assert not Animal.objects.filter(identificacao="AUD-ROLLBACK").exists()
