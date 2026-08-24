---
id: APP-RECOVERY-002
status: ready-for-dev
contract: ready-for-dev
---

# API 变更

## 新增公开端点

`GET /api/v1/app/auth/reset-password/open`

查询参数：

- `token`：必填，一次性密码重置 Token。
- `locale`：可选，`es`、`en` 或 `zh`；默认 `es`。

响应：

- `200 text/html`
- 页面中的主操作链接为 `eslatin://reset-password?token=<url-encoded-token>`。
- 响应必须设置禁止缓存、禁止索引和 no-referrer 安全头。

## 保持不变

- `POST /api/v1/app/auth/reset-password`
- `POST /api/v1/app/auth/confirm-reset-password`
- Token 长度、哈希方式、有效期和消费规则
