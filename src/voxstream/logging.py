"""JSON logging with a per-request correlation id. Logs lengths and counts, never text/audio."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
transport_var: ContextVar[str | None] = ContextVar("transport", default=None)

STAGE_ENGINE_INIT = "engine_init"
STAGE_SEGMENT_SYNTH = "segment_synth"
STAGE_CHUNK_SENT = "chunk_sent"
STAGE_REQUEST_END = "request_end"

logger = logging.getLogger("voxstream")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "transport": transport_var.get(),
            "msg": record.getMessage(),
        }
        stage = getattr(record, "stage", None)
        if stage:
            payload["stage"] = stage
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("voxstream")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


def log_stage(stage: str, *, text_chars: int | None = None, **counts: int | float | str) -> None:
    """Log a pipeline stage. ``text_chars`` is a length; text itself is never accepted."""
    fields: dict[str, Any] = dict(counts)
    if text_chars is not None:
        fields["chars"] = text_chars
    logger.info(stage, extra={"stage": stage, "fields": fields})
