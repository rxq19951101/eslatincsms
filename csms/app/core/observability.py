import time
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

trace_id_context: ContextVar[str] = ContextVar("trace_id", default="-")
request_count = 0
request_error_count = 0
try:
    from prometheus_client import Counter
    http_requests_total = Counter("csms_http_requests_total", "HTTP requests", ["method", "path"])
    http_errors_total = Counter("csms_http_errors_total", "HTTP 5xx responses")
except ImportError:
    http_requests_total = None
    http_errors_total = None


class TraceMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        global request_count, request_error_count
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        trace_id_context.set(trace_id)
        request.state.trace_id = trace_id
        request_count += 1
        if http_requests_total:
            http_requests_total.labels(request.method, request.url.path).inc()
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            request_error_count += 1
            if http_errors_total:
                http_errors_total.inc()
            raise
        if response.status_code >= 500:
            request_error_count += 1
            if http_errors_total:
                http_errors_total.inc()
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-Duration-Ms"] = str(round((time.monotonic() - started) * 1000, 2))
        return response
