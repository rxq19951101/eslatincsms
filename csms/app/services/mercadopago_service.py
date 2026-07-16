#
# Mercado Pago 支付服务封装
# 提供支付创建、状态查询、Webhook 验签、退款等功能
#

import os
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal

import mercadopago
from app.core.logging_config import get_logger

logger = get_logger("mercadopago_service")


def _extract_mp_api_error(result: Dict[str, Any]) -> str:
    """从 SDK 返回结果中解析可读错误（失败时常在 response.message / cause，顶层 message 可能为空）。"""
    parts: list[str] = []

    top_msg = result.get("message")
    if top_msg:
        parts.append(str(top_msg))

    resp = result.get("response")
    if isinstance(resp, dict):
        rmsg = resp.get("message")
        if rmsg and str(rmsg) not in parts:
            parts.append(str(rmsg))
        err = resp.get("error")
        if err:
            parts.append(str(err))
        causes = resp.get("cause")
        if isinstance(causes, list):
            for c in causes:
                if isinstance(c, dict):
                    desc = c.get("description") or c.get("code")
                    if desc:
                        parts.append(str(desc))
                elif c:
                    parts.append(str(c))
    elif isinstance(resp, str) and resp.strip():
        parts.append(resp.strip())

    return "; ".join(parts) if parts else "Unknown error"


class MercadoPagoService:
    """Mercado Pago 支付服务"""
    
    def __init__(self):
        self.environment = os.getenv("MERCADOPAGO_ENVIRONMENT", "sandbox")
        self.access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
        self.public_key = os.getenv("MERCADOPAGO_PUBLIC_KEY", "")
        self.webhook_secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")
        
        if not self.access_token:
            logger.warning("MercadoPago access token not configured. Payment features will not work.")
            self.sdk = None
        else:
            self.sdk = mercadopago.SDK(self.access_token)
    
    def generate_external_reference(self) -> str:
        """生成唯一外部参考号（格式：ESL-YYYYMMDD-{6位随机字符}）
        
        例如：ESL-20260120-A3F9K2
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_part = secrets.token_hex(3).upper()  # 6位随机字符
        return f"ESL-{today}-{random_part}"
    
    def create_payment(
        self,
        token: str,
        amount: Decimal,
        email: str,
        description: str,
        idempotency_key: str,
        device_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        external_reference: Optional[str] = None,
        payment_method_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建支付
        
        Args:
            token: 前端获取的 card token
            amount: 支付金额
            email: 用户邮箱（MP 强制要求）
            description: 支付描述（如 "EsLatin Carga - Station {station_id}"）
            idempotency_key: 幂等性键（UUID v4）
            device_id: 设备指纹（可选，防止风控）
            metadata: 元数据（可选）
            external_reference: 外部参考号（可选，如果不提供则自动生成）
        
        Returns:
            Dict 包含 payment_id, status, response 等
        """
        if not self.sdk:
            raise ValueError("MercadoPago SDK not initialized. Check access token configuration.")
        
        if not email:
            raise ValueError("Email is required by Mercado Pago")
        
        # 生成外部参考号
        if not external_reference:
            external_reference = self.generate_external_reference()
        
        pmid = (payment_method_id or "visa").strip().lower()

        # 构建支付数据
        payment_data = {
            "transaction_amount": float(amount),
            "token": token,
            "description": description,
            "installments": 1,
            "payment_method_id": pmid,
            "payer": {
                "email": email,
                "entity_type": "individual"
            },
            "external_reference": external_reference,
            "metadata": {
                "source": "eslatin_app",
                **(metadata or {})
            }
        }
        
        # 如果有设备指纹，添加到 metadata
        if device_id:
            payment_data["metadata"]["device_id"] = device_id
        
        # 设置请求选项（包含幂等性键）
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            "x-idempotency-key": idempotency_key
        }
        
        try:
            logger.info(f"Creating MercadoPago payment: external_reference={external_reference}, amount={amount}, email={email}")
            result = self.sdk.payment().create(payment_data, request_options)
            
            if result.get("status") == 201:
                response_data = result.get("response", {})
                logger.info(f"MercadoPago payment created: id={response_data.get('id')}, status={response_data.get('status')}")
                return {
                    "success": True,
                    "payment_id": str(response_data.get("id")),
                    "status": response_data.get("status"),
                    "external_reference": external_reference,
                    "response": response_data
                }
            else:
                error_message = _extract_mp_api_error(result)
                logger.error(
                    "MercadoPago payment creation failed: %s | http_status=%s | raw=%s",
                    error_message,
                    result.get("status"),
                    result,
                )
                return {
                    "success": False,
                    "error": error_message,
                    "response": result
                }
        except Exception as e:
            logger.error(f"Error creating MercadoPago payment: {str(e)}", exc_info=True)
            raise
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """查询支付状态
        
        Args:
            payment_id: Mercado Pago payment ID
        
        Returns:
            Dict 包含支付状态信息
        """
        if not self.sdk:
            raise ValueError("MercadoPago SDK not initialized. Check access token configuration.")
        
        try:
            result = self.sdk.payment().get(payment_id)
            
            if result.get("status") == 200:
                return {
                    "success": True,
                    "payment": result.get("response", {})
                }
            else:
                return {
                    "success": False,
                    "error": _extract_mp_api_error(result),
                }
        except Exception as e:
            logger.error(f"Error getting MercadoPago payment status: {str(e)}", exc_info=True)
            raise
    
    def verify_webhook_signature(
        self,
        x_signature: str,
        x_request_id: str,
        data_id: str
    ) -> bool:
        """验证 Webhook 签名
        
        Mercado Pago 的 x-signature 格式：ts=...,v1=...
        
        Args:
            x_signature: X-Signature header 值
            x_request_id: X-Request-Id header 值
            data_id: Webhook body 中的 data.id
        
        Returns:
            bool: 签名是否有效
        """
        if not self.webhook_secret:
            logger.warning("MercadoPago webhook secret not configured. Skipping signature verification.")
            return True  # 开发环境可能没有配置，允许通过
        
        try:
            # 解析 x-signature header
            # 格式：ts=1234567890,v1=abc123...
            parts = {}
            for part in x_signature.split(","):
                if "=" in part:
                    key, value = part.split("=", 1)
                    parts[key.strip()] = value.strip()
            
            ts = parts.get("ts")
            hash_v1 = parts.get("v1")
            
            if not ts or not hash_v1:
                logger.error("Invalid x-signature format")
                return False
            
            # 拼接 manifest
            manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
            
            # 计算 HMAC
            secret = self.webhook_secret.encode()
            calculated_hash = hmac.new(
                secret,
                manifest.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # 验证
            is_valid = calculated_hash == hash_v1
            if not is_valid:
                logger.warning(f"Webhook signature verification failed: calculated={calculated_hash}, received={hash_v1}")
            
            return is_valid
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}", exc_info=True)
            return False
    
    def refund_payment(self, payment_id: str, amount: Optional[Decimal] = None) -> Dict[str, Any]:
        """退款处理
        
        Args:
            payment_id: Mercado Pago payment ID
            amount: 退款金额（None 表示全额退款）
        
        Returns:
            Dict 包含退款结果
        """
        if not self.sdk:
            raise ValueError("MercadoPago SDK not initialized. Check access token configuration.")
        
        try:
            refund_data = {}
            if amount is not None:
                refund_data["amount"] = float(amount)
            
            logger.info(f"Creating refund for payment {payment_id}, amount={amount}")
            result = self.sdk.refund().create(payment_id, refund_data)
            
            if result.get("status") == 201:
                response_data = result.get("response", {})
                logger.info(f"Refund created: id={response_data.get('id')}, status={response_data.get('status')}")
                return {
                    "success": True,
                    "refund_id": str(response_data.get("id")),
                    "status": response_data.get("status"),
                    "response": response_data
                }
            else:
                error_message = _extract_mp_api_error(result)
                logger.error(f"Refund creation failed: {error_message}")
                return {
                    "success": False,
                    "error": error_message,
                    "response": result
                }
        except Exception as e:
            logger.error(f"Error creating refund: {str(e)}", exc_info=True)
            raise
    
    def map_status(self, mp_status: str) -> str:
        """映射 Mercado Pago 状态到内部状态
        
        Args:
            mp_status: Mercado Pago 状态（approved, rejected, cancelled, refunded, pending, in_process）
        
        Returns:
            内部状态（approved, declined, voided, refunded, processing）
        """
        status_map = {
            "approved": "approved",
            "rejected": "declined",
            "cancelled": "voided",
            "refunded": "refunded",
            "pending": "processing",
            "in_process": "processing"
        }
        return status_map.get(mp_status, "error")


# 单例模式
_mercadopago_service_instance = None


def get_mercadopago_service() -> MercadoPagoService:
    """获取 MercadoPago 服务实例（单例）"""
    global _mercadopago_service_instance
    if _mercadopago_service_instance is None:
        _mercadopago_service_instance = MercadoPagoService()
    return _mercadopago_service_instance
