#
# Mercado Pago 支付服务封装
# 提供支付创建、状态查询、Webhook 验签、退款等功能
#

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP

import mercadopago
from app.core.logging_config import get_logger
from app.services.payment_providers.credential_resolver import (
    CredentialResolver,
    EnvironmentCredentialResolver,
    ProviderCredentials,
)
from app.services.payment_providers.merchant_context import (
    MerchantAccountResolver,
    MerchantContext,
    PlatformMerchantAccountResolver,
)

logger = get_logger("mercadopago_service")


class MercadoPagoService:
    """Mercado Pago 支付服务"""

    _SAFE_PROVIDER_ERROR_FIELDS = (
        "error",
        "status_detail",
        "description",
        "code",
        "message",
    )

    _SENSITIVE_PROVIDER_TEXT = re.compile(
        r"(?:access[_ -]?token|card[_ -]?token|authorization|secret|password|cvv|pan)\s*[:=]\s*\S+",
        re.IGNORECASE,
    )
    _HIGH_ENTROPY_PROVIDER_TEXT = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")

    @classmethod
    def _safe_provider_text(cls, value: Any, *, field: str | None = None) -> str:
        """Bound provider text and redact likely credential material."""
        text = str(value)[:256]
        if cls._SENSITIVE_PROVIDER_TEXT.search(text):
            return cls._SENSITIVE_PROVIDER_TEXT.sub("[REDACTED]", text)
        if field in {"message", "description"} and cls._HIGH_ENTROPY_PROVIDER_TEXT.search(text):
            return "[REDACTED]"
        return text

    @classmethod
    def _safe_provider_error_details(cls, result: Any) -> Dict[str, Any]:
        """Return a bounded, allow-listed provider error projection.

        Never log the raw SDK response because it can contain credential,
        token, card, or request material. Keep only provider diagnostics that
        help support identify a rejected request.
        """
        if not isinstance(result, dict):
            return {"response_type": type(result).__name__}
        response = result.get("response")
        if not isinstance(response, dict):
            return {"response_type": type(response).__name__}

        details: Dict[str, Any] = {}
        for field in cls._SAFE_PROVIDER_ERROR_FIELDS:
            value = response.get(field)
            if isinstance(value, (str, int, float, bool)):
                details[field] = cls._safe_provider_text(value, field=field)

        cause = response.get("cause")
        if isinstance(cause, list):
            safe_causes = []
            for item in cause[:5]:
                if not isinstance(item, dict):
                    continue
                safe_item = {
                    key: cls._safe_provider_text(item[key], field=key)
                    for key in ("code", "description", "message")
                    if isinstance(item.get(key), (str, int, float, bool))
                }
                if safe_item:
                    safe_causes.append(safe_item)
            if safe_causes:
                details["cause"] = safe_causes

        return details or {
            "response_fields": sorted(str(key) for key in response.keys())[:20]
        }

    def _log_provider_rejection(self, *, operation: str, result: Any) -> None:
        status = result.get("status") if isinstance(result, dict) else None
        logger.error(
            "MercadoPago provider rejection: operation=%s http_status=%s "
            "environment=%s merchant_account_ref=%s details=%s",
            operation,
            status,
            self.environment,
            self.merchant_account_ref,
            self._safe_provider_error_details(result),
        )

    def _log_provider_exception(self, *, operation: str, exc: Exception) -> None:
        logger.error(
            "MercadoPago provider exception: operation=%s error_type=%s "
            "environment=%s merchant_account_ref=%s",
            operation,
            type(exc).__name__,
            self.environment,
            self.merchant_account_ref,
        )

    @staticmethod
    def _provider_transaction_amount(amount: Decimal) -> float:
        """Return the numeric JSON shape required by Mercado Pago.

        ``Decimal`` remains the money type throughout the domain and billing
        layers. The Mercado Pago SDK serializes the request with the standard
        JSON encoder. Mercado Pago's card-payment examples send this field as
        a JSON floating-point number, including whole amounts. Convert only
        at this provider boundary and keep the domain value as ``Decimal``;
        the value is rounded to the two-decimal payment precision before it
        becomes JSON. This avoids sending a string and keeps whole COP values
        compatible with the provider's sandbox validation.
        """
        normalized = Decimal(str(amount))
        if not normalized.is_finite():
            raise ValueError("Payment amount must be finite")
        if normalized.as_tuple().exponent < -2:
            raise ValueError("Payment amount must use at most two decimal places")
        return float(normalized.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    
    def __init__(
        self,
        *,
        credentials: ProviderCredentials,
        merchant_context: MerchantContext,
    ) -> None:
        if merchant_context.provider != "mercadopago":
            raise ValueError("Merchant context provider mismatch")
        self.environment = credentials.environment
        self.public_key = credentials.public_key
        self._webhook_secret = credentials.webhook_secret
        self.merchant_account_ref = merchant_context.merchant_account_ref
        self.sdk = mercadopago.SDK(credentials.access_token)
    
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
        if not email:
            raise ValueError("Email is required by Mercado Pago")
        
        # 生成外部参考号
        if not external_reference:
            external_reference = self.generate_external_reference()
        
        pmid = (payment_method_id or "visa").strip().lower()

        # 构建支付数据
        payment_data = {
            # The SDK's JSONEncoder cannot serialize Decimal. Convert only at
            # this provider boundary; the domain and reconciliation layers
            # continue to use Decimal.
            "transaction_amount": self._provider_transaction_amount(amount),
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
            request_shape = {
                key: type(value).__name__
                for key, value in payment_data.items()
                if key != "token"
            }
            request_shape["token"] = "present" if token else "missing"
            logger.info(
                "MercadoPago payment request diagnostics: external_reference=%s amount=%s "
                "amount_type=%s payment_method_id=%s request_shape=%s merchant_account_ref=%s",
                external_reference,
                amount,
                type(payment_data["transaction_amount"]).__name__,
                pmid,
                request_shape,
                self.merchant_account_ref,
            )
            started_at = time.monotonic()
            result = self.sdk.payment().create(payment_data, request_options)
            response = result.get("response") if isinstance(result, dict) else None
            logger.info(
                "MercadoPago payment provider response diagnostics: operation=create_payment "
                "http_status=%s elapsed_ms=%s response_type=%s response_fields=%s",
                result.get("status") if isinstance(result, dict) else None,
                round((time.monotonic() - started_at) * 1000, 2),
                type(response).__name__,
                sorted(str(key) for key in response.keys())[:20]
                if isinstance(response, dict)
                else [],
            )
            
            if result.get("status") == 201:
                response_data = result.get("response", {})
                logger.info(
                    "MercadoPago payment created: id=%s status=%s",
                    response_data.get("id"),
                    response_data.get("status"),
                )
                return {
                    "success": True,
                    "payment_id": str(response_data.get("id")),
                    "status": response_data.get("status"),
                    "external_reference": external_reference,
                    "next_action_url": self._safe_next_action_url(response_data),
                    "response": response_data,
                }
            else:
                self._log_provider_rejection(operation="create_payment", result=result)
                return {
                    "success": False,
                    "error": "mercadopago_payment_failed",
                    "response": result
                }
        except Exception as e:
            self._log_provider_exception(operation="create_payment", exc=e)
            raise

    @staticmethod
    def _request_options(idempotency_key: str):
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {"x-idempotency-key": idempotency_key}
        return request_options

    def create_customer(self, *, email: str, idempotency_key: str) -> Dict[str, Any]:
        if not email or not idempotency_key:
            raise ValueError("Customer email and idempotency key are required")
        try:
            result = self.sdk.customer().create(
                {"email": email}, self._request_options(idempotency_key)
            )
        except Exception as exc:
            self._log_provider_exception(operation="create_customer", exc=exc)
            raise
        status = result.get("status") if isinstance(result, dict) else None
        response = result.get("response") if isinstance(result, dict) else None
        customer_id = response.get("id") if isinstance(response, dict) else None
        if status not in {200, 201} or not customer_id:
            self._log_provider_rejection(operation="create_customer", result=result)
            return {"success": False, "error": "mercadopago_customer_creation_failed"}
        return {"success": True, "customer_id": str(customer_id)}

    def create_card(
        self,
        *,
        customer_id: str,
        token: str,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        if not customer_id or not token or not idempotency_key:
            raise ValueError("Customer, card token and idempotency key are required")
        try:
            result = self.sdk.card().create(
                customer_id,
                {"token": token},
                self._request_options(idempotency_key),
            )
        except Exception as exc:
            self._log_provider_exception(operation="create_card", exc=exc)
            raise
        status = result.get("status") if isinstance(result, dict) else None
        response = result.get("response") if isinstance(result, dict) else None
        if status not in {200, 201} or not isinstance(response, dict):
            self._log_provider_rejection(operation="create_card", result=result)
            return {"success": False, "error": "mercadopago_card_creation_failed"}
        payment_method = response.get("payment_method")
        payment_method = payment_method if isinstance(payment_method, dict) else {}
        return {
            "success": True,
            "customer_id": str(customer_id),
            "card_id": str(response.get("id")) if response.get("id") else None,
            "brand": payment_method.get("id") or response.get("payment_method_id"),
            "payment_type": payment_method.get("type") or response.get("payment_type_id"),
            "last_four": response.get("last_four_digits") or response.get("last_four"),
        }

    def delete_card(
        self,
        *,
        customer_id: str,
        card_id: str,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        if not customer_id or not card_id or not idempotency_key:
            raise ValueError("Customer, card and idempotency key are required")
        try:
            result = self.sdk.card().delete(
                customer_id, card_id, self._request_options(idempotency_key)
            )
        except Exception as exc:
            self._log_provider_exception(operation="delete_card", exc=exc)
            raise
        status = result.get("status") if isinstance(result, dict) else None
        if status in {200, 204}:
            return {"success": True}
        if status == 404:
            return {"success": True, "not_found": True}
        self._log_provider_rejection(operation="delete_card", result=result)
        return {"success": False, "error": "mercadopago_card_deletion_failed"}
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """查询支付状态
        
        Args:
            payment_id: Mercado Pago payment ID
        
        Returns:
            Dict 包含支付状态信息
        """
        try:
            result = self.sdk.payment().get(payment_id)
            
            if result.get("status") == 200:
                return {
                    "success": True,
                    "payment": result.get("response", {})
                }
            else:
                self._log_provider_rejection(operation="get_payment_status", result=result)
                return {
                    "success": False,
                    "error": "mercadopago_status_query_failed",
                }
        except Exception as e:
            self._log_provider_exception(operation="get_payment_status", exc=e)
            raise

    def get_refund_facts(self, payment_id: str) -> Dict[str, Any]:
        """Return the provider's cumulative refund fact for a payment.

        Refunds are intentionally not inferred from local metadata. Mercado
        Pago is the source of truth, while the caller stores only a compact
        local projection for idempotency and auditability.
        """
        try:
            refund_api = self.sdk.refund()
            list_method = getattr(refund_api, "list_all", None) or getattr(refund_api, "list", None)
            if not callable(list_method):
                raise RuntimeError("MercadoPago refund listing is unavailable")
            result = list_method(payment_id)
            if not isinstance(result, dict) or result.get("status") != 200:
                self._log_provider_rejection(operation="get_refund_facts", result=result)
                return {
                    "success": False,
                    "error": "mercadopago_refund_query_failed",
                    "retryable": True,
                }
            response = result.get("response")
            if isinstance(response, dict):
                entries = response.get("results")
                if entries is None:
                    entries = response.get("data")
                if entries is None:
                    entries = []
            else:
                entries = response
            # A successful refund query must contain a JSON object/list that
            # can be interpreted as a refund collection.  Do not turn an
            # empty string, HTML error page, or another malformed body into
            # "zero refunds"; that could incorrectly allow a second refund.
            if not isinstance(entries, list):
                self._log_provider_rejection(
                    operation="get_refund_facts",
                    result={"status": 200, "response": {"error": "invalid_refund_collection"}},
                )
                return {
                    "success": False,
                    "error": "mercadopago_refund_response_invalid",
                    "retryable": False,
                }
            refunded = Decimal("0.00")
            refund_ids = []
            for item in entries:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "approved").lower()
                if status in {"rejected", "cancelled", "canceled", "failed"}:
                    continue
                try:
                    refund_amount = Decimal(str(item.get("amount")))
                except (TypeError, ValueError, ArithmeticError):
                    return {
                        "success": False,
                        "error": "mercadopago_refund_response_invalid",
                    }
                if refund_amount <= 0:
                    continue
                refunded += refund_amount
                if item.get("id") is not None:
                    refund_ids.append(str(item["id"]))
            return {
                "success": True,
                "refunded_amount": refunded,
                "refund_ids": tuple(refund_ids),
            }
        except Exception as exc:
            self._log_provider_exception(operation="get_refund_facts", exc=exc)
            # The SDK may raise JSONDecodeError for an empty/non-JSON Provider
            # response.  Convert every adapter-boundary exception into a
            # stable, retryable failure so reconciliation remains fail-closed
            # without leaking SDK/parser details to the application layer.
            return {
                "success": False,
                "error": "mercadopago_refund_query_failed",
                "retryable": True,
            }

    def create_refund(
        self,
        payment_id: str,
        amount: Decimal,
        *,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """Create one refund attempt without returning the raw Provider body."""
        try:
            result = self.sdk.refund().create(
                payment_id,
                {"amount": amount},
                self._request_options(idempotency_key),
            )
            if not isinstance(result, dict) or result.get("status") not in {200, 201}:
                self._log_provider_rejection(operation="create_refund", result=result)
                return {
                    "success": False,
                    "error": "mercadopago_refund_failed",
                }
            response = result.get("response") or {}
            if not isinstance(response, dict):
                return {
                    "success": False,
                    "error": "mercadopago_refund_response_invalid",
                }
            return {
                "success": True,
                "refund_id": str(response["id"]) if response.get("id") is not None else None,
                "status": str(response.get("status") or "approved"),
                "amount": Decimal(str(response.get("amount", amount))),
            }
        except Exception as exc:
            self._log_provider_exception(operation="create_refund", exc=exc)
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
            secret = self._webhook_secret.encode()
            calculated_hash = hmac.new(
                secret,
                manifest.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # 验证
            # Use constant-time comparison for the provider trust boundary.
            # Plain equality can leak prefix information through timing.
            is_valid = hmac.compare_digest(calculated_hash, hash_v1)
            if not is_valid:
                logger.warning("Webhook signature verification failed")
            
            return is_valid
        except Exception as e:
            logger.error("Error verifying webhook signature: %s", type(e).__name__)
            return False
    
    def refund_payment(self, payment_id: str, amount: Optional[Decimal] = None) -> Dict[str, Any]:
        """退款处理
        
        Args:
            payment_id: Mercado Pago payment ID
            amount: 退款金额（None 表示全额退款）
        
        Returns:
            Dict 包含退款结果
        """
        try:
            refund_data = {}
            if amount is not None:
                refund_data["amount"] = self._provider_transaction_amount(amount)
            
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
                self._log_provider_rejection(operation="refund_payment", result=result)
                return {
                    "success": False,
                    "error": "mercadopago_refund_failed",
                    "response": result
                }
        except Exception as e:
            self._log_provider_exception(operation="refund_payment", exc=e)
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
            "canceled": "voided",
            "refunded": "refunded",
            "expired": "expired",
            "timeout": "expired",
            "pending": "processing",
            "in_process": "processing"
        }
        return status_map.get(mp_status, "error")

    @staticmethod
    def _safe_next_action_url(payment: Dict[str, Any]) -> Optional[str]:
        candidates = [
            payment.get("redirect_url"),
            payment.get("init_point"),
            (payment.get("point_of_interaction") or {})
            .get("transaction_data", {})
            .get("external_resource_url"),
            (payment.get("three_ds_info") or {}).get("external_resource_url"),
        ]
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            if candidate.startswith("https://") and len(candidate) <= 2048:
                return candidate
        return None


def get_mercadopago_service(
    *,
    merchant_context: MerchantContext | None = None,
    merchant_resolver: MerchantAccountResolver | None = None,
    credential_resolver: CredentialResolver | None = None,
) -> MercadoPagoService:
    """Build a merchant-scoped service without globally cached credentials.

    ``merchant_context=None`` is a temporary C1 compatibility bridge for the
    existing routes. New payment flows must provide a context resolved from
    trusted server-side tenant data. BE-6 removes the bridge.
    """
    if merchant_context is None:
        resolver = merchant_resolver or PlatformMerchantAccountResolver()
        if not isinstance(resolver, PlatformMerchantAccountResolver):
            raise ValueError("Explicit merchant context is required")
        merchant_context = resolver.resolve_legacy_platform_context()

    credentials = (credential_resolver or EnvironmentCredentialResolver()).resolve(
        merchant_context
    )
    return MercadoPagoService(
        credentials=credentials,
        merchant_context=merchant_context,
    )
