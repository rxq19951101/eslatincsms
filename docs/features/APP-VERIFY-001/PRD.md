---
id: APP-VERIFY-001
status: ready-for-dev
owner: product
---

# Web 邮箱验证码输入修复

## 问题

邮箱验证码页面使用覆盖整个内容区的 `TouchableWithoutFeedback` 调用 `Keyboard.dismiss()`。在 React Native Web 中，点击输入框后事件会冒泡到外层并立即让输入框失焦；同时 `autoFocus` 会再次请求焦点，造成输入框反复弹出、无法稳定输入。

## 目标

- Web 用户可以稳定聚焦验证码输入框并输入 6 位数字。
- Web 页面不自动抢占输入焦点。
- iOS 和 Android 继续支持点击空白区域收起键盘。
- 继续限制为 6 位纯数字，提交逻辑和 API 契约不变。

## 非范围

- 不修改验证码 API、邮件发送或注册流程。
- 不处理密码重置邮件链接；该问题单独处理。
