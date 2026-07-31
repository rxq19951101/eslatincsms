---
id: APP-RECOVERY-001
status: ready-for-dev
---

# 验收标准

1. App 在中文、英语、西语环境请求重置时，API 分别提交 `zh`、`en`、`es`。
2. 后端分别生成对应语言的邮件主题、按钮、有效期、安全提示和备用链接。
3. 未提供 `locale` 的旧客户端仍可请求重置，并收到默认西语邮件。
4. 非法 `locale` 不会产生任意模板选择或 HTML 注入。
5. 新原生构建可识别 `eslatin://reset-password?token=...`，并将 token 传给 `ResetPassword` 页面。
6. 邮件同时包含纯文本版本和响应式 HTML 版本；HTML 不依赖 JavaScript、远程字体或内嵌脚本。
7. 不在日志、响应或邮件正文中泄露除一次性重置 URL 之外的敏感凭据。
8. 前后端相关单元测试、TypeScript 检查和后端针对性测试通过。

