# Frontend Boundaries

## 1. App 与 Admin

- App 面向车主旅程；Admin 面向平台/租户运营。不得因组件相似而共享身份、导航或业务状态。
- 两端只通过 Backend frozen API contract 获取事实，不访问数据库、Redis 或 Provider secret API。

## 2. App 分层

- `api/`：HTTP transport、契约映射和安全错误分类。
- `features/`：跨屏但单领域的协调器，例如 Checkout 恢复与 GET 去重。
- `store/`：跨屏业务状态；不得保存 PAN/CVV/证件/Card Token。
- `screens/`：用户流程和 UI 状态，不发明后端字段。
- `components/`：展示和交互，不承担租户授权或结算。
- `navigation/`：Deep Link allowlist、参数长度和恢复入口。
- `i18n/`：三语言业务状态映射；未知状态安全回退。

## 3. Admin 分层

- `app/` 定义路由和页面组合；`features/` 组织领域 UI；`components/` 提供复用展示；`lib/` 提供 API/auth/i18n 工具。
- Admin 客户端只提供操作意图；后端裁决角色、租户和状态迁移。
- 地图和公开构建变量不得包含服务端 secret。

## 4. 支付边界

- App/Admin 不渲染自建 PAN/CVV/证件字段；卡敏感字段只在托管 Checkout Secure Fields。
- App 只存 checkout_session_id、purpose、expiresAt/source 等非敏感恢复引用。
- `save_card=true` 只允许独立保存卡 flow；charging direct/top-up 固定 false。
- Deep Link 仅作导航触发，服务端 GET 是状态事实；409/503/网络未知不得自动新建 Checkout。
- 未知 card/payment status 不猜成 credit/success。

## 5. 禁止

- UI 中复制计费、退款、权限和租户授权算法。
- 使用 fake data 隐藏后端契约缺陷。
- 将 Provider 原始错误、敏感 URL 或 token 写入日志/状态。
- 前端单方面改变 frozen API。
- 公共组件依赖具体支付/OCPP 业务服务。

## 6. Frontend Agent 门禁

frontend-agent 启动时读取产品架构、技术架构、本文件、相关 ADR 和 frozen contract。跨 App/Admin 或改变 API/共享业务状态的任务至少按 C2 评估。
