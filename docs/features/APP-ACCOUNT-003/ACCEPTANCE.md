---
id: APP-ACCOUNT-003
status: ready-for-dev
---

# 验收标准

1. 点击退出登录后显示国际化确认弹窗。
2. 点击取消只关闭弹窗，不 dispatch 登出 action。
3. 点击确认只 dispatch 一次登出 action，提交期间不能重复触发。
4. 登出 action 完成后进入 `Welcome` 页面。
5. Web 与原生端使用一致的确认行为。
6. 不修改登出 API、Token 清理、Redux 和导航契约。
7. 账户页直接相关测试和 App TypeScript 检查通过。
