---
id: PAY-MP-002
change_id: CHG-20260812-002
status: product-baseline-updated
owner: product
---

# PAY-MP-002 产品决策

本文件只记录 PAY-MP-002 的产品决策和待决问题。D-201、D-202、D-203、D-204-B、D-205～D-210 已有有效用户批准记录；D-204-B 已完成产品基线更新，下一门禁是独立架构审核。任何产品批准均不等同于架构、API、数据库、Provider、部署或实现批准，也不改变 PAY-MP-001 的 A1/B1/C1/D1、D-008 或 D-017。

## 1. 新增产品决策提案

| 编号 | 决策 | 推荐/候选选择 | 原因 | 影响范围 | 状态 |
|---|---|---|---|---|---|
| D-201 | 公开上线欠费恢复 | **已批准：** P0 交付账单列表、详情、按账单全额补缴、处理中恢复、最终结清后 D1 解锁；部分补缴仍未批准 | D1 阻断必须与可理解、可执行的恢复闭环配对 | App/backend/shared | user-approved |
| D-202 | 补缴支付方式 | **已批准：** 支持新卡、已保存卡（CVV）和钱包；可用方式由服务端按账单和 Provider 状态决定 | 覆盖现有 PAY-MP-001 支付能力，避免强制某一种方式 | App/backend | user-approved |
| D-203 | 充电前风险控制路线 | **已批准方案 1：保持 PAY-MP-001 A1，充电结束后按准确 Invoice 金额扣款，并通过量化风险预算控制敞口。支付层必须保留 Provider 无关的扩展空间；未批准任何具体后续 Provider 或路由规则。** 方案 2 保留为未批准候选。 | 用户先保证系统可用，同时为后续多支付平台接入保留边界 | product/backend/operations | user-approved |
| D-204 | 风险预算边界（仅方案 1） | **已批准 D-204-B：** 单会话 200,000 COP / 100 kWh / 180 分钟，任一先到即停止；用户未结敞口 250,000 COP；站点/平台使用同一 UTC 滚动 24 小时窗口，无午夜重置；站点敞口 1,000,000 COP、平台敞口 5,000,000 COP；active reservation 与 unresolved 计入，已释放/已结算不计入；MeterValues 120 秒降级、300 秒自动停止；离线/unknown 额外敞口 15,000 COP 或 5 分钟；Provider unknown 自动核查 24 小时且不重复扣款；RemoteStop 10 秒内发起、最多自动重试 3 次；StopTransaction 目标 5 分钟；15 分钟内自动恢复核查、24 小时内最终处理。 | 将后付敞口转化为可审计且优先自动闭环的业务规则 | product/risk/operations/backend | user-approved; architecture-review-required |
| D-205 | 历史与收据 | **已批准 D-205-A：** P0 只提供 App 内基础充电历史/详情和支付结果；不提供 PDF/下载/邮件收据，也不提供 DIAN 电子发票 | 先以最小历史能力保证用户可查，降低首发范围 | App/backend | user-approved |
| D-206 | 退款/拒付用户体验 | **已批准 D-206-B：** 结构化问题/退款工单；双人控制全额/部分退款；状态透明；首次人工响应 1 工作日、目标决定 3 工作日 | 兼顾用户恢复、财务控制和可审计性 | App/Admin/backend/operations/finance | user-approved |
| D-207 | 对账完成定义 | **已批准 D-207-B：** 持续逐笔匹配 + 每日 EsLatin/Provider/实际资金三方对账；仅时序/手续费差异允许双人批准的 24 小时临时例外；次工作日 12:00 Bogotá 前完成 | 以可证明资金闭环控制首发风险，并保留 Provider-neutral 扩展 | backend/Admin/finance | user-approved |
| D-208 | 紧急关闭 | **已批准 D-208-B：** 收费充电准入与支付轨双轴、分范围关闭；一人可关闭、不同人员批准恢复；不自动恢复，不因支付关闭强停活跃会话 | 控制事故敞口并保留支付、设备和对账事实收敛 | backend/Admin/operations/security | user-approved |
| D-209 | 支持入口 | **已批准 D-209-B：** 上下文 App 工单 + 邮件通知 + 公开收费站点在其营业时段内的实时紧急支持渠道；支持人员不能改写财务事实 | 减少定位时间，保护敏感数据并覆盖充电安全场景 | App/Admin/operations | user-approved |
| D-210 | 发布等级 | **已批准 D-210-B：** R0 沙盒、R1 生产暗启动、R2 内部真实支付、R3 封闭测试、R4 人工批准公开上线；采用决策请求中的 R2/R3 建议限额与零容忍门禁 | 用分阶段真实资金证据降低公开发布爆炸半径 | product/QA/operations | user-approved |

## 2. 与 PAY-MP-001 的关系

- A1、B1、C1、D1 保持原批准事实。
- D-008 在 PAY-MP-002 中被定义为公开上线前必须补齐的产品缺口，但在负责人批准并实现前，D-008 的原状态不变。
- D-017 的既有 PAY-MP-001 事实保持不变；D-203 方案 1 已是当前产品方向，方案 2 仍是未批准候选，不得被写成当前实现路线或 deferred/non-goal。
- D-203 方案 1 和 D-204-B 已获得用户批准，产品基线已更新；D-204-B 仍需架构、契约、实现和 QA 门禁。未完成这些门禁前不得声称 P002 已完成或允许真实资金收费。
- D-205-A 明确排除可下载/PDF/邮件收据和 DIAN 电子发票；后续若需要这些能力，必须新建或重新开启产品决策，不得从“基础历史”推断。
- D-206-B、D-207-B、D-208-B、D-209-B、D-210-B 的详细流程、SLA、权限和分阶段数值以 `PRODUCT_DECISION_REQUEST.md` 中对应已选择方案为产品输入；仍需技术架构、冻结契约、QA/E2E 和人工放行。
- “后续会接其他支付平台，留拓展空间”只批准 Provider-neutral extension principle，不批准具体 Provider、路由、费率、分账、结算或技术实现。
- guest、PSE、Nequi、现金、分期和 C2 租户分账继续保持非范围。

## 3. 技术问题，不由本文件决定

| 编号 | 技术问题 | 后续 owner | 阻塞范围 |
|---|---|---|---|
| Q-201 | 未来若重新启用方案 A，Mercado Pago Colombia 当前支付路径是否支持预授权、最终捕获、部分捕获、释放、追加、3DS、保存卡和退款的完整组合？ | architecture/backend/provider | future / non-blocking |
| Q-202 | 补缴是否复用现有 Invoice/PaymentOrder/Checkout，如何在并发、重复回调和状态未知时保持原账单不可变？ | architecture/backend | P0-A |
| Q-203 | D1 解锁与退款、拒付、部分退款、资金未释放和处理中的状态如何形成唯一服务端判定？ | architecture/backend | P0-A/P0-D |
| Q-204 | 基础历史、支付结果、退款和拒付采用现有事实的查询投影、读模型还是新领域对象；异步事件边界是什么？ | architecture/backend | P0-C/P0-D |
| Q-205 | 紧急关闭的配置、权限、双人审批、审计、作用域和恢复如何避免前端直接控制生产开关？ | architecture/backend/security | P0-D |
| Q-206 | 对账和异常队列如何处理重放、批次、资金释放、手续费、拒付冻结及数据库写入压力？ | architecture/backend/finance | P0-D |
| Q-207 | App/Admin 需要的最小共享状态与错误语义是什么，如何不把 Provider 原始 payload 冻结到公共契约？ | architecture/frontend/backend | P0-A/P0-C |
| Q-208 | 是否新增数据库迁移、事件或外部 webhook；若需要，兼容、回滚、空库和历史数据策略是什么？ | architecture-agent | 全部 P0 |

## 4. 决策门禁

在完成 D-204-B 的 Q-202/Q-203/Q-205 架构结论、契约更新和 QA 证据前：

- 不能宣称公开上线资金风险已解决。
- 不能把 D-204-B 的产品参数直接当作已完成的技术实现或运行时证据。
- 方案 2 的预授权/最终捕获研究可以作为候选任务保留，但不能在用户选择前被写成当前实现路线或非目标。
- 不能启用生产支付轨、部署生产配置或开始真实公开收费。
