"""
Coral logging setup.

Provides:
- RichHandler for pretty terminal output
- JSON rotating file logs → logs/coral.log
- request_id context var propagated through all log records

Usage (every module):
    # from app.core.logger import get_logger
    # logger = get_logger(__name__)

Setup (call once at process start, before any imports that log):
    # from app.core.logger import configure_logging
    # configure_logging()
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.logging import RichHandler

# ── Request-ID context variable ───────────────────────────────────────────────
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return request_id_var.get("")


# ── JSON formatter ────────────────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line with a stable set of fields."""

    _STANDARD = frozenset(
        {
            "args", "created", "exc_info", "exc_text", "filename", "funcName",
            "levelname", "levelno", "lineno", "message", "module", "msecs",
            "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "taskName", "thread", "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

        entry: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "request_id": get_request_id() or record.__dict__.get("request_id", ""),
        }

        for key in (
            "stage", "route", "intent", "duration_ms", "status_code", "error",
            "method", "path", "confidence", "rows_used", "chunks_retrieved",
            "sql_summary", "result_count", "sources",
        ):
            val = record.__dict__.get(key)
            if val is not None:
                entry[key] = val

        for k, v in record.__dict__.items():
            if k not in self._STANDARD and k not in entry:
                entry[k] = v

        if record.exc_info:
            entry["traceback"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["traceback"] = record.exc_text

        return json.dumps(entry, default=str)


# ── Request-ID injection filter ───────────────────────────────────────────────

class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", ""):
            record.request_id = get_request_id()
        return True


# ── Build handlers ────────────────────────────────────────────────────────────

def _build_rich_handler(level: int) -> logging.Handler:
    handler = RichHandler(
        level=level,
        show_time=True,
        show_path=True,
        rich_tracebacks=True,
        markup=True,
        log_time_format="[%H:%M:%S]",
    )
    handler.addFilter(_RequestIDFilter())
    return handler


def _build_file_handler(log_path: Path, level: int) -> logging.Handler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(_JSONFormatter())
    handler.addFilter(_RequestIDFilter())
    return handler


# ── Public configuration entry point ─────────────────────────────────────────

def configure_logging(log_dir: Path | None = None) -> None:
    """
    Configure root logger once at process startup.

    Reads from environment:
        LOG_LEVEL       — default INFO
        DEBUG / CORAL_DEBUG — forces DEBUG when true
    """
    raw_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    debug_env = os.environ.get("DEBUG", "") or os.environ.get("CORAL_DEBUG", "")
    if debug_env.lower() in ("1", "true", "yes"):
        raw_level = "DEBUG"

    level = getattr(logging, raw_level, logging.INFO)

    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_path = log_dir / "coral.log"

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    root.addHandler(_build_rich_handler(level))

    file_handler_ok = False
    try:
        root.addHandler(_build_file_handler(log_path, level))
        file_handler_ok = True
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("coral.logger").warning(
            "Could not open log file %s: %s", log_path, exc
        )

    # Modules that still use structlog.get_logger() delegate to our root logger.
    try:
        import structlog
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    except Exception:  # noqa: BLE001
        pass

    for noisy in ("httpx", "httpcore", "urllib3", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("coral.logger").info(
        "logging_configured level=%s rich=true json_file=%s path=%s",
        raw_level,
        file_handler_ok,
        str(log_path) if file_handler_ok else "disabled",
    )


# ── Module-level convenience ──────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """Return a standard Logger for `name`."""
    return logging.getLogger(name)
