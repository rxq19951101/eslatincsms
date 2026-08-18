---
id: PAY-MP-002-FE-201
change_id: CHG-20260812-002
feature_id: PAY-MP-002
scope: frontend
owner: frontend-agent
status: repaired-awaiting-fresh-independent-frontend-qa
---

# FE-201 前端契约 Adapter、状态与 i18n 基线交接

## STATUS

`repaired-awaiting-fresh-independent-frontend-qa`

本交接只覆盖 FE-201。App/Admin 分别建立了 `PAY-MP-002-v1` 的 typed adapter、状态安全映射和三语言文案基线；没有实现 FE-202+、D-204/BE-205、生产配置或真实支付。

前一轮 blocker 修复收紧了 App `normalizeRecoveryAttempt` 的边界：缺失 5.3 RecoveryAttempt 必需字段时返回 `RESPONSE_INVALID`；RecoveryAttempt、allocation、financial eligibility 和 next action 均按冻结字段白名单重建。

本次针对 fresh frontend QA 新发现的 Admin blocker，`decodeRefundCase`、`decodeRail`、`decodeSupportCase` 及其 approval/actor/target/scope/timeline/linked resource 嵌套投影均改为 allowlist 重建，不保留 `pan`、`cvv`、`raw_provider_payload` 或其他未知字段。最新独立 QA 报告保持原样，需由 qa-agent fresh rerun 后关闭 gate。

本次针对第二次 fresh frontend QA 新发现的 App blocker，P002 transaction adapter 按 frozen §5.7 的 12 个字段显式重建，并移除 `P002TransactionProjection` 的开放 index signature；`unknown_field`、`pan`、`cvv`、`raw_provider_payload` 不再进入 transaction projection。最新独立 QA 报告保持原样，需由 qa-agent fresh rerun 后关闭 gate。

本次针对最新独立 QA 的最终 blocker，P002 transaction adapter 对 12 个 frozen 字段补齐必填性、类型、UTC 时间和 Decimal/nullable runtime 校验；非法 projection 统一 `RESPONSE_INVALID` fail closed。P001/P002 协商、Hosted boundary 和既有 allowlist 保持不变。最新独立 QA 报告保持原样，需由 qa-agent fresh rerun 后关闭 gate。

## CHANGED_FILES

- `app/src/features/payMp002/types.ts`
- `app/src/features/payMp002/status.ts`
- `app/src/features/payMp002/adapter.ts`
- `app/src/features/payMp002/__tests__/adapter.test.ts`
- `app/src/features/payMp002/__tests__/fe201_qa_boundary.test.ts`（仅补全 QA 边界测试夹具）
- `admin/lib/payMp002Types.ts`
- `admin/lib/payMp002Status.ts`
- `admin/lib/payMp002.ts`
- `admin/lib/__tests__/payMp002.test.ts`
- `admin/lib/api.ts`（canonical error code/reference/retryable/retry-after 扩展，保持原构造参数兼容）
- `app/src/i18n/es.ts`
- `app/src/i18n/en.ts`
- `app/src/i18n/zh.ts`
- `admin/lib/i18n.tsx`
- `docs/features/PAY-MP-002/frontend/FE-201_HANDOFF.md`

工作区中其他前端、后端、迁移、配置和文档改动均为既有改动，未回退、未清理、未取得所有权。

## COMMANDS_RUN

- `npm test -- --runInBand src/features/payMp002/__tests__/adapter.test.ts`
- `npm test -- lib/__tests__/payMp002.test.ts`
- `npm test -- --runInBand src/features/payMp002/__tests__/adapter.test.ts src/i18n/__tests__/i18nIntegrity.test.ts src/features/payment/__tests__/checkoutCoordinator.test.ts src/api/__tests__/client.test.ts src/api/__tests__/charging.contract.test.ts`
- `npm test -- lib/__tests__/payMp002.test.ts lib/__tests__/localization.test.ts lib/__tests__/api-error-handling.test.ts`
- `npx tsc --noEmit --pretty false`（App）
- `npx tsc --noEmit --pretty false`（Admin，顺序重跑）
- `npx next build --webpack`（Admin）
- `git diff --check`

本次 blocker 修复追加：

- `npm test -- --runInBand src/features/payMp002/__tests__/adapter.test.ts src/features/payMp002/__tests__/fe201_qa_boundary.test.ts`
- `npx tsc --noEmit --pretty false`（App）
- `npm test -- lib/__tests__/payMp002.test.ts`（Admin）
- `npx tsc --noEmit --pretty false`（Admin）
- `npx next build --webpack`（Admin）

首次并发运行 Admin typecheck 与 `npm run build` 时，typecheck 遇到 `.next/types` 尚在生成；同一次默认 Turbopack build 因沙箱禁止绑定端口失败。随后顺序 Admin typecheck 通过，`npx next build --webpack` 完整通过。

## TEST_RESULTS

- App FE-201 focused：`9 passed`
- Admin FE-201 focused：`5 passed`
- App FE-201 + P001 相邻回归/i18n：`5 suites, 33 passed`
- Admin FE-201 + localization/error handling：`3 files, 21 passed`
- App typecheck：passed
- Admin typecheck：passed
- Admin webpack production build：passed，17 routes generated
- App i18n integrity：Spanish/English/Chinese key parity passed
- `git diff --check`：passed
- blocker repair focused tests：2 suites / 11 tests passed；QA 的缺失字段和敏感字段边界均通过
- App P002 transaction allowlist boundary：新增后 2 suites / 12 tests passed
- App P002 transaction schema boundary：新增后 2 suites / 13 tests passed，非法必填/类型/UTC/Decimal 输入均 fail closed
- App typecheck：passed；App package 无 build script
- Admin FE-201 test：5 passed；Admin typecheck：passed；Admin webpack build：passed，17 routes generated

本次 Admin blocker 修复追加：

- `npm test -- lib/__tests__/payMp002.test.ts`：6 passed
- App 相关回归（含 FE-201 App boundary）：6 suites / 35 tests passed
- App/Admin typecheck：passed
- `npx next build --webpack`（Admin）：passed，17 routes generated
- `git diff --check`：passed

本次 P002 transaction blocker 修复追加：

- `npm test -- --runInBand src/features/payMp002/__tests__/adapter.test.ts src/features/payMp002/__tests__/fe201_qa_boundary.test.ts`：2 suites / 12 tests passed
- P002 runtime schema boundary：2 suites / 13 tests passed
- App/Admin 相关回归、typecheck、Admin webpack build 和 `git diff --check`：passed

## CONTRACT_CHANGES

- 无 API、public contract、database、migration 或 event contract 变更。
- Adapter 仅消费冻结的 `PAY-MP-002-v1`：cursor envelope、canonical errors、CF-201 状态映射、P001/P002 `Accept` 协商、Decimal string、UTC/safe refs 和 Admin 幂等意图头。

## ARCHITECTURE_COMPLIANCE

- C3 / CHG-20260812-002 / ADR-005：遵守已批准目标架构；前端只拥有 projection 和用户意图。
- App/Admin 运行时状态与 adapter 分离，不共享 store；Admin P002 请求不构造 dummy/platform tenant。
- `provider_approved→approved`、`committed→confirmed`、`needs_review→unknown`、`recheck_required→evaluating` 固定；未知 enum fail closed。
- RecoveryAttempt 必需字段、嵌套 allocation/eligibility/next_action 字段和 UTC/Decimal 类型在 adapter 边界校验；未知 projection 字段不进入返回对象。
- App/Admin projection 均按 frozen contract allowlist 重建；`pan`、`cvv`、`raw_provider_payload` 不进入 projection；Hosted boundary 未改变。
- P002 transaction projection 严格重建 frozen §5.7 字段，P001 bare-array/旧 number-null projection 保持不变。
- P002 12 字段逐项校验必填性、string/number/null 类型、UTC 格式和 Decimal string；非法输入返回 `RESPONSE_INVALID`。
- duplicate approval 固定为 `manual_review`、`reason_code=duplicate_approval`、`allocation=null`。
- Decimal numeric projection、非法 cursor body、非法 Hosted URL 和 `FinancialEligibility` 中的 `rail_closed` fail closed；失败响应不降级为 empty。
- Hosted sensitive boundary、P001 bare-array/offset/number-null 兼容、server-side D1/amount/tenant/RBAC/rail authority 保持。
- 未触碰后端业务、冻结契约、数据库迁移、生产配置、D-204 风险参数或真实支付。

## RISKS

- 独立 `qa-agent` fresh frontend QA、跨模块 E2E、人工审查和生产发布门禁仍未完成；本交接不是 QA 或生产批准。
- App 默认 `npm run build` 不存在；已完成 App typecheck 和相关 Jest 回归。Admin 默认 Turbopack build 受沙箱端口限制，webpack build 通过。
- FE-202+ 页面/完整欠费旅程、Admin 业务工作台和后端联调未在 FE-201 范围内实现。
- D-204/BE-205、`PAYMENT_RAILS_ENABLED` 生产门禁和真实支付继续保持 blocked/no-go。
