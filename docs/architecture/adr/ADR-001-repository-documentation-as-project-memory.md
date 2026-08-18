# ADR-001 — Repository Documentation as Persistent Project Memory

- Status: accepted
- Date: 2026-08-12
- Related Change ID: CHG-20260812-001

## Context

项目经历多个临时 Agent 和长链路功能开发。Feature 文档能保存局部事实，但没有全局当前产品/技术架构；物理 Agent nickname 和线程并不稳定。

## Decision

以 `PRODUCT_ARCHITECTURE.md` 和 `TECH_ARCHITECTURE.md` 作为当前全局事实源，以 ADR 记录重大原因，以 Change/feature 文档记录需求、计划和证据。Agent 每次从仓库重建上下文；物理线程仅是临时工作记忆。

## Reason

版本化文档可审查、可追溯、可由任意未来 Agent 读取，不依赖线程存活或 nickname。

## Alternatives Considered

- 固定长期运行的 Agent 保存上下文。
- 只使用 feature 文档。
- 把所有历史按时间追加到一个架构日志。

## Rejected Alternatives

线程会结束且上下文会压缩；feature 文档缺乏完整当前视图；时间堆叠不能清楚表达当前系统。

## Consequences

- C2/C3 增加文档和审查成本。
- 当前架构必须随有意变更整体更新。
- 文档漂移成为 QA 缺陷，不再默认代码正确。

## Affected Modules

工程治理、所有未来产品和技术变更。
