#
# 通知服务：Email / Webhook
#

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger("ocpp_csms")


class NotificationService:
    """告警与业务事件通知"""

    @staticmethod
    def _webhook_url() -> Optional[str]:
        return os.getenv("ALERT_WEBHOOK_URL", "").strip() or None

    @staticmethod
    def _smtp_configured() -> bool:
        return bool(os.getenv("SMTP_HOST", "").strip())

    @staticmethod
    async def send_alert_notification(
        title: str,
        description: str,
        severity: str,
        charge_point_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        payload = {
            "title": title,
            "description": description,
            "severity": severity,
            "charge_point_id": charge_point_id,
            "tenant_id": tenant_id,
        }
        await NotificationService._send_webhook(payload)
        await NotificationService._send_email(
            subject=f"[CSMS {severity}] {title}",
            body=description or title,
        )

    @staticmethod
    async def _send_webhook(payload: dict) -> None:
        url = NotificationService._webhook_url()
        if not url:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            logger.info("Alert webhook delivered: %s", payload.get("title"))
        except Exception as e:
            logger.error("Alert webhook failed: %s", e)

    @staticmethod
    async def _send_email(subject: str, body: str) -> None:
        if not NotificationService._smtp_configured():
            return
        try:
            import smtplib
            from email.mime.text import MIMEText

            host = os.getenv("SMTP_HOST")
            port = int(os.getenv("SMTP_PORT", "587"))
            user = os.getenv("SMTP_USER", "")
            password = os.getenv("SMTP_PASSWORD", "")
            from_addr = os.getenv("SMTP_FROM", user)
            to_addrs = [
                a.strip()
                for a in os.getenv("ALERT_EMAIL_TO", "").split(",")
                if a.strip()
            ]
            if not to_addrs:
                return

            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = ", ".join(to_addrs)

            use_ssl = (
                os.getenv("SMTP_SSL", "").lower() in ("true", "1", "yes")
                or port == 465
            )
            use_tls = (
                os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")
                and not use_ssl
            )
            smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
            with smtp_class(host, port, timeout=15) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
            logger.info("Alert email sent: %s", subject)
        except Exception as e:
            logger.error("Alert email failed: %s", e)
