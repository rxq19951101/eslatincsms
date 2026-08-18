---
id: PRC-MODE-001
status: ready-for-dev
---

# 实施任务

- [x] BE-1：建立统一 PricingMode/Tariff 解析服务，兼容旧 JSON 和旧正价 Tariff。
- [x] BE-2：更新站点与充电桩定价接口、校验、版本化和审计日志。
- [x] BE-3：将有效定价加入投运门禁、公开查询和扫码启动门禁。
- [x] BE-4：在会话创建时固化 PricingSnapshot，结算只使用快照并删除租户任意 Tariff 兜底。
- [x] FE-1：Admin 支持站点 paid/free/unavailable 和桩级 inherit/paid/free/unavailable。
- [x] FE-2：Admin 显示 COP、有效模式、来源、原因和截止时间。
- [x] APP-1：App 正确展示 paid/free，不把 null 转为 0；不可用设备不进入公开列表和启动流程。
- [ ] QA-1：覆盖解析优先级、免费期限、投运/启动阻断、快照锁价、免费结算和租户隔离。
- [x] QA-2：执行后端、Admin、App 定向回归并形成 QA_REPORT.md。
