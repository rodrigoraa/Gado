from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Emite uma linha JSON válida sem incluir dados de request ou segredos."""

    def format(self, record: logging.LogRecord) -> str:
        dados: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            dados["exception"] = self.formatException(record.exc_info)
        return json.dumps(dados, ensure_ascii=False)
