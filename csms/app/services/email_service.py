#
# 用户事务邮件（验证码、重置密码等）
#

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 加载 csms/.env（SMTP 等本地密钥，勿提交）
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

logger = logging.getLogger("ocpp_csms")


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip())


def send_user_email(
    to_addr: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> bool:
    """发送用户邮件。未配置 SMTP 时写入日志并返回 False（开发可看日志拿验证码）。"""
    to_addr = (to_addr or "").strip()
    if not to_addr:
        return False

    if not smtp_configured():
        logger.warning(
            "SMTP not configured; email not sent to %s | subject=%s | body=%s",
            to_addr,
            subject,
            text_body.replace("\n", " | "),
        )
        return False

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user) or user
    # SMTP_SSL=true 或端口 465 → 使用隐式 SSL（Spaceship Spacemail）
    use_ssl = (
        os.getenv("SMTP_SSL", "").lower() in ("true", "1", "yes")
        or port == 465
    )
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes") and not use_ssl

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("User email sent to %s | subject=%s | from=%s", to_addr, subject, from_addr)
        return True
    except Exception as e:
        logger.error("User email failed to %s: %s", to_addr, e)
        return False
