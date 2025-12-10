#
# 中间件
# 请求日志、错误处理、CORS等
#

import time
import logging
import json
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

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
        user_agent = request.headers.get("user-agent", "unknown")
        
        # 获取查询参数
        query_params = dict(request.query_params)
        
        # 获取请求体（如果是 POST/PUT/PATCH）
        body = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    try:
                        body = json.loads(body_bytes.decode())
                    except:
                        body = body_bytes.decode()[:500]  # 限制长度
                # 重新创建请求对象（因为 body 已经被读取）
                async def receive():
                    return {"type": "http.request", "body": body_bytes}
                request._receive = receive
            except Exception as e:
                logger.debug(f"无法读取请求体: {e}")
        
        # 判断是否记录请求开始日志（先假设会成功，实际在响应时再判断）
        should_log_request = True
        if client_host in ("127.0.0.1", "::1", "localhost") and request.url.path == "/health":
            should_log_request = False
        
        # 记录请求开始（如果需要）
        if should_log_request:
            logger.info(
                f"[API请求] {request.method} {request.url.path} | "
                f"客户端: {client_host} | "
                f"查询参数: {query_params if query_params else '无'}",
                extra={
                    "event": "api_request_start",
                    "method": request.method,
                    "path": request.url.path,
                    "client_host": client_host,
                    "user_agent": user_agent,
                    "query_params": query_params,
                    "request_body": body,
                }
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
                
                logger.log(
                    log_level,
                    f"[API响应] {request.method} {request.url.path} | "
                    f"状态码: {status_code} | "
                    f"耗时: {process_time:.3f}s | "
                    f"客户端: {client_host}",
                    extra={
                        "event": "api_request_complete",
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "process_time": process_time,
                        "client_host": client_host,
                        "response_size": response_body_size,
                    }
                )
            
            # 添加处理时间头
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"[API错误] {request.method} {request.url.path} | "
                f"错误: {str(e)} | "
                f"耗时: {process_time:.3f}s | "
                f"客户端: {client_host}",
                extra={
                    "event": "api_request_error",
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "process_time": process_time,
                    "client_host": client_host,
                    "query_params": query_params,
                    "request_body": body,
                },
                exc_info=True
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

