---
id: APP-RECOVERY-001
status: ready-for-dev
owner: product
---

# App 密码重置链接与品牌邮件治理

## 背景

密码重置邮件当前直接使用 `eslatin://reset-password`，现有 iOS 构建无法正确打开；App 导航也未声明 deep-link 路由。邮件固定为英语且版式简陋，未使用客户在 App 中选择的语言。

## 范围

- App 请求密码重置时提交当前语言 `locale`，允许 `es`、`en`、`zh`。
- 后端按请求语言生成西语、英语或中文的密码重置主题、纯文本和品牌化 HTML；未提供或非法语言时默认西语。
- HTML 邮件包含品牌头、明确主按钮、30 分钟有效期、安全提示和可复制的备用链接，并兼容常见邮件客户端。
- App 导航容器声明 `eslatin://reset-password?token=...` 到 `ResetPassword` 页面之间的映射。
- 保留 `eslatin` 原生 scheme，并为配置与路由增加自动化测试。
- API 对旧客户端保持兼容：`locale` 为可选字段。

## 非范围

- 不接入新的邮件供应商。
- 不修改 Token 有效期、密码规则和账户安全策略。
- 本任务不配置 Apple Universal Links、Android App Links 或网页重置页面。
- 已安装的旧 TestFlight 构建不会自动获得原生 scheme，需重新构建并安装。

