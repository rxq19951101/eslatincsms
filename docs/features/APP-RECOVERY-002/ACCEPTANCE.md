---
id: APP-RECOVERY-002
status: ready-for-dev
---

# 验收标准

1. 密码重置邮件 HTML 按钮和纯文本备用链接均为 `https://api.eslatin.com.co/...` 形式，不直接使用 `eslatin://`。
2. HTTPS 中转页包含一次性 Token 对应的 App Deep Link，但不自动消费 Token。
3. 中转页提供中文、英文和西班牙文，非法 locale 回退西班牙文。
4. Token 和 locale 均安全 URL 编码/HTML 转义，不允许模板注入。
5. 中转页响应包含 `Cache-Control: no-store`、`Referrer-Policy: no-referrer`、`X-Robots-Tag: noindex, nofollow`。
6. 现有 `POST /reset-password` 和 `POST /confirm-reset-password` 契约保持不变。
7. 后端直接相关测试通过。
8. 更新并重建本地 CSMS 后，新邮件显示可点击 HTTPS 重置入口。
