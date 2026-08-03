---
id: CHG-LIFECYCLE-001
status: passed
tested_at: 2026-08-02
scope: admin-focused
---

# Admin QA 记录

## 结论

Admin 生命周期聚焦组件与集成回归通过，未发现阻止进入端到端集成验收的前端缺陷。本轮仅补充 QA 测试，不修改业务实现，不增加数据库迁移。

## 覆盖矩阵

| 验收范围 | 测试证据 | 结果 |
| --- | --- | --- |
| 退役桩不在普通站点数据与正常计数中 | 资产过滤辅助测试、站点详情测试及后端查询过滤测试 | 通过 |
| 充电桩退役预检与阻塞反馈 | `chargers/[id]/__tests__/page.test.tsx` | 通过 |
| 站点归档预检、阻塞项和处理入口 | `sites/[id]/__tests__/page.test.tsx` | 通过 |
| 退役、归档、恢复交互 | 充电桩和站点详情测试 | 通过 |
| 永久删除精确确认 | 充电桩和站点详情测试 | 通过 |
| API 失败时保留确认流程并显示错误 | 新增退役提交失败和归档预检失败用例 | 通过 |
| 退役设备隐藏远程控制和二维码操作 | 充电桩详情测试 | 通过 |
| 资产归档列表、筛选和历史入口 | `asset-archive/__tests__/page.test.tsx` | 通过 |
| 普通 Dashboard、交易与站点筛选兼容 | Dashboard 与交易集成测试 | 通过 |

## 执行结果

```text
6 test files passed
27 tests passed
ESLint passed
TypeScript passed
```

## 浏览器检查说明

系统层面确认 Docker Desktop 正在监听 `*:3000`，应用内浏览器也成功打开
`http://localhost:3000`（页面标题为 `EsLatin - Admin Portal`）。当前浏览器会话随后跳转到登录页，
没有可用于本轮验证的有效登录态，因此本项通过证据仍来自 Vitest 组件/集成测试，未声称完成已登录状态下的真实浏览器联调。

## 剩余范围

- 端到端集成验收尚未执行。
- 真实浏览器与后端联合运行验证纳入下一项集成验收。
- 生产阶段专用生命周期字段和迁移仍按计划延期。
