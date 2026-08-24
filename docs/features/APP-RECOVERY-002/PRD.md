---
id: APP-RECOVERY-002
status: ready-for-dev
owner: product
---

# 密码重置邮件 HTTPS 链接

## 问题

密码重置邮件直接使用 `eslatin://` 自定义协议。Gmail 等邮件客户端会过滤或不展示非 HTTP(S) 链接，导致用户看不到可点击的重置入口。当前本地 CSMS 容器还运行旧版纯文本邮件模板。

## 目标

- 邮件中的按钮和备用链接必须使用公开 HTTPS 地址。
- HTTPS 页面显示 EsLatin 品牌、链接有效期说明和“打开 EsLatin”按钮。
- 用户点击页面按钮后通过 `eslatin://reset-password?token=...` 打开 App。
- 页面提供中文、英文、西班牙文，并与请求密码重置时的 locale 一致。
- 页面禁止缓存、禁止搜索引擎索引、禁止发送 Referer。
- Token 继续只在最终确认密码时消费，现有 30 分钟有效期不变。

## 非范围

- 不建立 Apple Universal Links 或 Android App Links。
- 不修改密码复杂度、Token 哈希、Token 有效期或确认密码 API。
- 不修改 App 重置密码页面。
