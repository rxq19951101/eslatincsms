#
# API 日志工具函数
# 提供统一的 API 日志记录接口
#

import logging
from typing import Dict, Any, Optional
from fastapi import Request

logger = logging.getLogger("ocpp_csms")


def get_user_info(current_user: Any = None, request: Optional[Request] = None) -> str:
    """
    从请求上下文提取用户信息
    支持多种用户对象类型：dict、AppUser、AdminUser等
    """
    if not current_user:
        # 尝试从 request.state 获取
        if request and hasattr(request.state, "current_user"):
            current_user = request.state.current_user
    
    if not current_user:
        return "anonymous"
    
    # 如果是字典（JWT payload）
    if isinstance(current_user, dict):
        user_id = current_user.get("user_id") or current_user.get("id")
        user_type = current_user.get("user_type", "unknown")
        if user_id:
            return f"{user_type}:{user_id}"
        return f"{user_type}:unknown"
    
    # 如果是对象
    if hasattr(current_user, "id"):
        user_id = str(current_user.id)
        user_type = getattr(current_user, "user_type", None) or getattr(current_user, "__class__", type).__name__
        return f"{user_type}:{user_id}"
    
    return "unknown"


def mask_sensitive_data(data: Any, sensitive_keys: list = None) -> Any:
    """
    脱敏敏感数据
    默认敏感字段：password, token, secret, key
    """
    if sensitive_keys is None:
        sensitive_keys = ["password", "token", "secret", "key", "access_token", "refresh_token"]
    
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            k_lower = k.lower()
            if any(sensitive in k_lower for sensitive in sensitive_keys):
                if isinstance(v, str):
                    masked[k] = f"{v[:4]}***" if len(v) > 4 else "***"
                else:
                    masked[k] = "***"
            else:
                masked[k] = v
        return masked
    return data


def log_api_request(
    method: str,
    path: str,
    operation: str,
    user_info: str = None,
    params: Dict[str, Any] = None,
    current_user: Any = None,
    request: Optional[Request] = None,
):
    """
    记录 API 请求入口日志
    """
    if user_info is None:
        user_info = get_user_info(current_user, request)
    
    # 脱敏敏感参数
    safe_params = mask_sensitive_data(params) if params else {}
    
    # 构建参数字符串
    params_str = ""
    if safe_params:
        param_items = []
        for k, v in safe_params.items():
            if isinstance(v, str) and len(v) > 50:
                v = f"{v[:50]}..."
            param_items.append(f"{k}={v}")
        params_str = " | " + " | ".join(param_items)
    
    logger.info(
        f"[API] {method} {path} | operation={operation} | user={user_info}{params_str}"
    )


def log_api_response(
    method: str,
    path: str,
    operation: str,
    result: str,
    user_info: str = None,
    details: Dict[str, Any] = None,
    current_user: Any = None,
    request: Optional[Request] = None,
):
    """
    记录 API 成功响应日志
    """
    if user_info is None:
        user_info = get_user_info(current_user, request)
    
    details_str = ""
    if details:
        detail_items = []
        for k, v in details.items():
            if isinstance(v, str) and len(v) > 50:
                v = f"{v[:50]}..."
            detail_items.append(f"{k}={v}")
        details_str = " | " + " | ".join(detail_items)
    
    logger.info(
        f"[API] {method} {path} | operation={operation} | result={result} | user={user_info}{details_str}"
    )


def log_api_error(
    method: str,
    path: str,
    operation: str,
    error: Exception,
    user_info: str = None,
    params: Dict[str, Any] = None,
    current_user: Any = None,
    request: Optional[Request] = None,
    exc_info: bool = True,
):
    """
    记录 API 错误日志
    """
    if user_info is None:
        user_info = get_user_info(current_user, request)
    
    # 脱敏敏感参数
    safe_params = mask_sensitive_data(params) if params else {}
    
    error_msg = str(error)
    error_type = type(error).__name__
    
    params_str = ""
    if safe_params:
        param_items = []
        for k, v in safe_params.items():
            if isinstance(v, str) and len(v) > 50:
                v = f"{v[:50]}..."
            param_items.append(f"{k}={v}")
        params_str = " | " + " | ".join(param_items)
    
    logger.error(
        f"[API错误] {method} {path} | operation={operation} | user={user_info} | "
        f"error_type={error_type} | error={error_msg}{params_str}",
        exc_info=exc_info
    )


def log_business_operation(
    operation: str,
    entity_type: str,
    entity_id: Any,
    result: str,
    user_info: str = None,
    details: Dict[str, Any] = None,
    current_user: Any = None,
    request: Optional[Request] = None,
):
    """
    记录业务操作日志
    """
    if user_info is None:
        user_info = get_user_info(current_user, request)
    
    details_str = ""
    if details:
        detail_items = []
        for k, v in details.items():
            if isinstance(v, str) and len(v) > 50:
                v = f"{v[:50]}..."
            detail_items.append(f"{k}={v}")
        details_str = " | " + " | ".join(detail_items)
    
    logger.info(
        f"[API] {operation} | {entity_type}={entity_id} | result={result} | user={user_info}{details_str}"
    )
