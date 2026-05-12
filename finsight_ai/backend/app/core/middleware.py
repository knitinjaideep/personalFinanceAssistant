"""
Request-tracing middleware.

For every incoming HTTP request:
- Generates a UUID request_id (or adopts X-Request-ID from the caller).
- Sets it on request.state.request_id and in the request_id_var context variable
  so all downstream log calls within the same async task inherit it.
- Adds X-Request-ID to the response.
- Logs request_started, request_completed, and request_failed with Rich + JSON.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logger import get_logger, request_id_var

logger = get_logger("coral.middleware")


class RequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        request.state.request_id = req_id

        start = time.perf_counter()
        logger.info(
            "request_started",
            extra={
                "stage": "request_started",
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,
            },
        )

        try:
            response: Response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            response.headers["X-Request-ID"] = req_id
            logger.info(
                "request_completed",
                extra={
                    "stage": "request_completed",
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.error(
                "request_failed",
                extra={
                    "stage": "request_failed",
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise
        finally:
            request_id_var.reset(token)
