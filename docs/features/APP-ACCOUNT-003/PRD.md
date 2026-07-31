---
id: APP-ACCOUNT-003
status: ready-for-dev
owner: product
---

# App 退出登录交互修复

## 问题

账户页使用 React Native `Alert.alert` 确认退出登录。该交互在 Web 端没有可靠实现，用户点击“退出登录”后没有可见反馈。

## 目标

- 点击“退出登录”后，在 Web 和原生端都显示明确的二次确认。
- 取消操作不得调用登出 action。
- 确认操作只调用一次登出 action，提交期间禁止重复点击。
- 登出完成后进入欢迎页。

## 实现范围

- 复用 `APP-ACCOUNT-002` 已建立的跨平台 `ConfirmationDialog`。
- 复用现有中文、英文、西班牙文登出文案。
- 增加账户页退出登录直接测试。

## 非范围

- 不修改后端登出 API、Token 清理逻辑、Redux action 或导航参数。
- 不调整账户页其他功能和视觉结构。
