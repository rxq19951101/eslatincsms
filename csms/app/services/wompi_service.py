#
# Wompi 支付服务封装
# 提供 reference 生成、integrity_signature 生成、Webhook 验签、对账等功能
#

import os
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal

import httpx
from app.core.logging_config import get_logger

logger = get_logger("wompi_service")


class WompiService:
    """Wompi 支付服务"""
    
    def __init__(self):
        self.environment = os.getenv("WOMPI_ENVIRONMENT", "sandbox")
        self.base_url = os.getenv(
            "WOMPI_BASE_URL",
            "https://sandbox.wompi.co/v1" if self.environment == "sandbox" else "https://production.wompi.co/v1"
        )
        
        # 根据环境选择密钥
        if self.environment == "sandbox":
            self.public_key = os.getenv("WOMPI_PUBLIC_KEY_SANDBOX", "")
            self.private_key = os.getenv("WOMPI_PRIVATE_KEY_SANDBOX", "")
        else:
            self.public_key = os.getenv("WOMPI_PUBLIC_KEY_PROD", "")
            self.private_key = os.getenv("WOMPI_PRIVATE_KEY_PROD", "")
        
        self.integrity_secret = os.getenv("WOMPI_INTEGRITY_SECRET", "")
        
        if not self.public_key or not self.private_key:
            logger.warning("Wompi keys not configured. Payment features will not work.")
    
    def generate_reference(self) -> str:
        """生成唯一 reference（格式：ESL-YYYYMMDD-{6位随机字符}）
        
        例如：ESL-20260120-A3F9K2
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_part = secrets.token_hex(3).upper()  # 6位随机字符
        return f"ESL-{today}-{random_part}"
    
    def generate_integrity_signature(
        self,
        reference: str,
        amount_in_cents: int,
        currency: str = "COP"
    ) -> str:
        """生成完整性签名（根据 Wompi 文档要求）
        
        Wompi 的 integrity signature 生成规则：
        SHA256(reference + amount_in_cents + currency + integrity_secret)
        """
        if not self.integrity_secret:
            logger.error("WOMPI_INTEGRITY_SECRET not configured")
            raise ValueError("Integrity secret not configured")
        
        # 拼接字符串
        data = f"{reference}{amount_in_cents}{currency}{self.integrity_secret}"
        
        # 计算 SHA256
        signature = hashlib.sha256(data.encode()).hexdigest()
        
        return signature
    
    def create_payment_checkout_data(
        self,
        reference: str,
        amount: Decimal,
        currency: str = "COP",
        redirect_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """准备 Widget/Web Checkout 所需数据（reference + integrity_signature）
        
        Returns:
            Dict containing payment data for frontend
        """
        # 金额转换为分（cents）
        amount_in_cents = int(amount * 100)
        
        # 生成完整性签名
        integrity_signature = self.generate_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency
        )
        
        return {
            "public_key": self.public_key,
            "reference": reference,
            "integrity_signature": integrity_signature,
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "redirect_url": redirect_url or "",
        }
    
    def verify_webhook_signature(
        self,
        payload: Dict[str, Any],
        signature_header: Optional[str] = None
    ) -> bool:
        """验证 Wompi Webhook 签名（events checksum）。"""
        events_secret = os.getenv("WOMPI_EVENTS_SECRET", "").strip()
        if not events_secret:
            if self.environment == "sandbox":
                logger.warning("WOMPI_EVENTS_SECRET not set; skipping verification in sandbox")
                return True
            logger.error("WOMPI_EVENTS_SECRET not configured for production")
            return False

        sig = payload.get("signature") or {}
        properties = sig.get("properties") or []
        checksum = sig.get("checksum")
        if not checksum:
            logger.error("Webhook missing signature.checksum")
            return False

        tx = payload.get("data", {}).get("transaction") or {}
        chain = "".join(str(tx.get(prop, "")) for prop in properties)
        timestamp = str(payload.get("timestamp", ""))
        raw = f"{chain}{timestamp}{events_secret}"
        expected = hashlib.sha256(raw.encode()).hexdigest().upper()
        return hmac.compare_digest(expected, checksum.upper())
    
    async def get_transaction_status(
        self,
        transaction_id: str
    ) -> Optional[Dict[str, Any]]:
        """查询 Wompi 交易状态（GET /transactions/{id}，用于二次确认）
        
        Returns:
            Transaction data from Wompi API or None if error
        """
        if not self.private_key:
            logger.error("Wompi private key not configured")
            return None
        
        url = f"{self.base_url}/transactions/{transaction_id}"
        headers = {
            "Authorization": f"Bearer {self.private_key}",
            "Content-Type": "application/json",
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get transaction status from Wompi: {e}")
            return None
    
    async def get_merchant_info(self) -> Optional[Dict[str, Any]]:
        """获取商户信息（GET /merchants/{public_key}，如需要 acceptance tokens）
        
        Returns:
            Merchant data from Wompi API or None if error
        """
        if not self.public_key or not self.private_key:
            logger.error("Wompi keys not configured")
            return None
        
        url = f"{self.base_url}/merchants/{self.public_key}"
        headers = {
            "Authorization": f"Bearer {self.private_key}",
            "Content-Type": "application/json",
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get merchant info from Wompi: {e}")
            return None
    
    def validate_amount_and_currency(
        self,
        order_amount: Decimal,
        order_currency: str,
        wompi_amount: Decimal,
        wompi_currency: str
    ) -> Tuple[bool, Optional[str]]:
        """验证订单金额/币种 == Wompi 交易金额/币种（防串单/篡改）
        
        Returns:
            (is_valid, error_message)
        """
        # 转换为分进行比较（Wompi 使用分）
        order_amount_cents = int(order_amount * 100)
        wompi_amount_cents = int(wompi_amount * 100)
        
        if order_amount_cents != wompi_amount_cents:
            error_msg = (
                f"Amount mismatch: order={order_amount_cents} cents, "
                f"wompi={wompi_amount_cents} cents"
            )
            logger.error(error_msg)
            return False, error_msg
        
        if order_currency != wompi_currency:
            error_msg = (
                f"Currency mismatch: order={order_currency}, "
                f"wompi={wompi_currency}"
            )
            logger.error(error_msg)
            return False, error_msg
        
        return True, None


# 全局实例
_wompi_service: Optional[WompiService] = None


def get_wompi_service() -> WompiService:
    """获取 Wompi 服务实例（单例模式）"""
    global _wompi_service
    if _wompi_service is None:
        _wompi_service = WompiService()
    return _wompi_service
