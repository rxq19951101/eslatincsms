#
# 中间件
# 请求日志、错误处理、CORS等
#

import time
import logging
import json
import traceback
import hashlib
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.core.observability import trace_id_context
from app.core.log_sanitization import redact_log_text, redact_sensitive_data

logger = logging.getLogger("ocpp_csms")


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 - 记录所有 API 请求和响应（过滤本地健康检查）"""
    
    def _should_log(self, client_host: str, path: str, status_code: int) -> bool:
        """
        判断是否应该记录日志
        过滤规则：
        1. 来自 127.0.0.1 的 /health 请求且状态码为 200 的，不记录
        2. 所有错误（状态码 >= 400）都记录
        3. 其他情况正常记录
        """
        # 如果是错误，始终记录
        if status_code >= 400:
            return True
        
        # 如果是本地健康检查且成功，不记录
        if client_host in ("127.0.0.1", "::1", "localhost") and path == "/health" and status_code == 200:
            return False
        
        # 其他情况正常记录
        return True
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 获取客户端信息
        client_host = request.client.host if request.client else "unknown"
        request_headers = redact_sensitive_data(dict(request.headers))
        user_agent = request_headers.get("user-agent", "unknown")
        
        # 获取查询参数
        query_params = redact_sensitive_data(dict(request.query_params))
        
        # 获取请求体（如果是 POST/PUT/PATCH）
        body = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    try:
                        body = redact_sensitive_data(json.loads(body_bytes.decode()))
                    except:
                        body = redact_sensitive_data(body_bytes.decode()[:500])
                # 重新创建请求对象（因为 body 已经被读取）
                async def receive():
                    return {"type": "http.request", "body": body_bytes}
                request._receive = receive
            except Exception as e:
                logger.debug("无法读取请求体: %s", redact_log_text(str(e)))
        
        # 判断是否记录请求开始日志（先假设会成功，实际在响应时再判断）
        should_log_request = True
        if client_host in ("127.0.0.1", "::1", "localhost") and request.url.path == "/health":
            should_log_request = False
        
        # 记录请求开始（如果需要）
        if should_log_request:
            request_extra = redact_sensitive_data({
                "event": "api_request_start",
                "method": request.method,
                "path": request.url.path,
                "client_host": client_host,
                "user_agent": user_agent,
                "request_headers": request_headers,
                "query_params": query_params,
                "request_body": body,
                "trace_id": trace_id_context.get(),
            })
            logger.info(
                f"[API请求] trace_id={trace_id_context.get()} {request.method} {request.url.path} | "
                f"客户端: {client_host} | "
                f"查询参数: {query_params if query_params else '无'}",
                extra=request_extra,
            )
        
        # 处理请求
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # 获取响应体大小
            response_body_size = None
            if hasattr(response, "body"):
                try:
                    response_body_size = len(response.body) if response.body else 0
                except:
                    pass
            
            # 判断是否应该记录响应日志
            status_code = response.status_code
            should_log_response = self._should_log(client_host, request.url.path, status_code)
            
            # 记录响应完成（如果需要）
            if should_log_response:
                log_level = logging.INFO if status_code < 400 else logging.WARNING if status_code < 500 else logging.ERROR
                
                response_extra = redact_sensitive_data({
                    "event": "api_request_complete",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "process_time": process_time,
                    "client_host": client_host,
                    "response_size": response_body_size,
                    "trace_id": trace_id_context.get(),
                })
                logger.log(
                    log_level,
                    f"[API响应] {request.method} {request.url.path} | "
                    f"状态码: {status_code} | "
                    f"耗时: {process_time:.3f}s | "
                    f"客户端: {client_host}",
                    extra=response_extra,
                )
            
            # 添加处理时间头
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            safe_error = redact_log_text(str(e))
            error_extra = redact_sensitive_data({
                "event": "api_request_error",
                "method": request.method,
                "path": request.url.path,
                "error": safe_error,
                "error_type": type(e).__name__,
                "process_time": process_time,
                "client_host": client_host,
                "request_headers": request_headers,
                "query_params": query_params,
                "request_body": body,
                "trace_id": trace_id_context.get(),
                "stack_frames": traceback.format_tb(e.__traceback__),
            })
            logger.error(
                f"[API错误] {request.method} {request.url.path} | "
                f"错误: {safe_error} | "
                f"耗时: {process_time:.3f}s | "
                f"客户端: {client_host}",
                extra=error_extra,
            )
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # 仅在HTTPS时添加
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """进程内滑动窗口限流。

    匿名请求按来源 IP 限流；认证请求使用令牌指纹隔离，并按接口类别分桶，
    避免同一 NAT/Docker 网关下的 App 和 Admin 相互耗尽额度。
    """

    def __init__(self, app: ASGIApp, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._hits: dict[str, list[float]] = {}
        self._last_cleanup = 0.0

    @staticmethod
    def _client_identity(request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
            return f"auth:{fingerprint}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    @staticmethod
    def _route_bucket(path: str) -> str:
        buckets = (
            "/api/v1/app/charging",
            "/api/v1/dashboard",
            "/api/v1/admin",
            "/api/v1/sites",
        )
        for prefix in buckets:
            if path.startswith(prefix):
                return prefix
        return "/api/v1"

    def _cleanup_stale_buckets(self, now: float, window_start: float) -> None:
        if now - self._last_cleanup < 60:
            return
        self._hits = {
            key: [hit for hit in hits if hit > window_start]
            for key, hits in self._hits.items()
            if any(hit > window_start for hit in hits)
        }
        self._last_cleanup = now

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS" or request.url.path.startswith(("/health", "/metrics", "/ocpp", "/docs")):
            return await call_next(request)

        now = time.time()
        window_start = now - 60
        self._cleanup_stale_buckets(now, window_start)
        key = f"{self._client_identity(request)}:{self._route_bucket(request.url.path)}"
        hits = [hit for hit in self._hits.get(key, []) if hit > window_start]
        if len(hits) >= self.requests_per_minute:
            retry_after = max(1, int(60 - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Rate limit exceeded",
                        "details": [],
                        "status_code": 429,
                    },
                },
            )
        hits.append(now)
        self._hits[key] = hits
        return await call_next(request)
