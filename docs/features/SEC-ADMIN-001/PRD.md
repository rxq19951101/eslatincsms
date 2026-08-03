---
id: SEC-ADMIN-001
status: ready-for-dev
---

# Admin 前端依赖安全治理

## 背景

Admin 当前依赖审计报告包含 3 个生产依赖高风险项，以及 3 个来自 Vitest 工具链的 critical 项，不满足生产发布要求。

## 目标

- 将 Next.js 升级到已修复当前已知漏洞的同一主版本。
- 将 Vitest、Vitest UI、覆盖率插件和 Vite 升级到兼容的安全版本。
- 更新直接 PostCSS 依赖并刷新传递依赖锁定版本。
- 保持现有业务功能、页面路由和 API 使用方式不变。

## 范围

- `admin/package.json`
- `admin/package-lock.json`
- Admin 定向测试、生产构建和 npm 安全审计

## 非目标

- 不修改 Admin 业务页面或交互。
- 不修改后端 API、数据库或部署环境。
- 不执行强制大版本升级。

## 冻结版本

- Next.js：`16.2.12`
- Vitest、`@vitest/ui`、`@vitest/coverage-v8`：`4.1.10`
- Vite：`7.3.6`
- PostCSS：`8.5.25`
