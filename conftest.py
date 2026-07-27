from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def isolar_arquivos_gerados(settings: Any) -> Iterator[None]:
    """Impede que uploads dos testes contaminem a pasta media real."""
    with TemporaryDirectory(prefix="gestao-rural-testes-") as temporario:
        raiz = Path(temporario)
        media = raiz / "media"
        media.mkdir()
        settings.MEDIA_ROOT = media
        yield
