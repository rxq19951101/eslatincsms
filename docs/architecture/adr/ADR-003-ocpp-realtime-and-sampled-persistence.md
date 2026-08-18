# ADR-003 — OCPP Realtime State and Sampled Persistence

- Status: accepted
- Date: 2026-08-12
- Related Change ID: PERF-DB-001 / PERF-DB-002

## Context

Heartbeat 和 MeterValues 频率高。逐条永久写入会导致数据库写放大、索引增长和长期存储压力，但在线状态、当前功率和账单用量仍需可靠。

## Decision

Redis 保存短期在线/心跳/实时计量快照和去重；PostgreSQL 保存会话边界、计费需要的用量事实和受控时间采样。重复 OCPP 消息通过短期幂等键抑制；不能恢复无界 HeartbeatHistory 写入。

## Reason

把实时可丢弃状态与审计/计费持久事实分离，降低数据库压力，同时保持会话和账单可追溯。

## Alternatives Considered

- 每次心跳和计量值都永久落库。
- 完全不保存计量历史。
- 只使用 Redis 保存全部会话和计量。

## Rejected Alternatives

全量写入不可扩展；不持久化无法计费/审计；Redis 丢失不能破坏会话和账单事实。

## Consequences

- 运营图表的原始粒度受采样策略限制。
- 采样间隔和账单计算必须分别测试。
- 未来时序数据库属于 C2/C3，需要兼容和迁移分析。

## Affected Modules

OCPP message handler、Redis state、MeterValue/Session、monitoring、billing。
