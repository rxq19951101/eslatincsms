# Codex Project Agent & Architecture Governance

## 1. 核心原则

- Agent 是临时执行器；仓库文档是项目持久记忆和事实来源。
- 决策顺序必须是：当前产品架构 → 当前技术架构 → ADR → 任务计划 → 实现 → QA → 必要时 E2E。
- Agent 的物理 nickname 可能变化，逻辑身份只由角色前缀决定；不得依赖聊天记忆恢复项目事实。
- `docs/product/PRODUCT_ARCHITECTURE.md` 描述完整的当前产品；`docs/architecture/TECH_ARCHITECTURE.md` 描述完整的当前技术架构。二者不是按时间追加的日志。
- C2/C3 需求必须先完成影响分析和架构审查，禁止收到需求后直接写业务代码。
- 根主线程负责调度、产品决策确认、文档审查和交接；不直接承担大段前后端业务实现。

## 1.1 Human Product Decision Gate

产品负责人（用户）是重大产品选择的唯一批准者。Agent 可以分析事实、提出多个候选方案、说明取舍并给出推荐，但推荐、技术可行性、历史相似决定或“优先保证可用性”都不等于用户批准。

### 重大产品决策范围

以下决定必须由用户明确选择或批准后才能成为产品事实：

- 选择或排除互斥的产品方案、支付/收费/资金风险模型、预授权/后付/扣款时序、退款/拒付和资金责任；
- 金额、价格、预算、损失上限、计费、结算、欠费恢复、D1 阻断/解锁、免费/不可用等规则；
- 身份验证、访客/登录、卡保存、支付方式、用户资格、隐私/合规和消费者承诺；
- 租户/收款主体/分账/权限责任、运营人工处置、支持 SLA、发布范围、P0/P1 优先级和非目标；
- 会改变用户旅程、运营流程、外部支付/设备行为或生产开关的任何其他业务选择。

### 强制请求与停止规则

1. `product-agent` 可以把候选方案写入当前 change draft，必须把推荐与已批准事实分开；不得自行把任一方案写入有效产品基线、已批准 ADR、实现就绪任务或生产配置。
2. 遇到尚未由用户决定的重大选择，`product-agent` 必须创建 `docs/changes/<CHANGE_ID>/PRODUCT_DECISION_REQUEST.md`，列出决策编号、候选方案、影响、推荐（如有）、待用户回答的精确问题，并将状态设为 `awaiting-user-approval`。
3. 输出 `PRODUCT DECISION REQUEST` 后，product-agent 必须停止；不得继续触发最终 `architecture-agent` 审核、契约冻结或实施 Agent。
4. 根主线程收到 `awaiting-user-approval` 后必须向用户展示正式请求并询问具体选项；不得代替用户决定，也不得继续调用最终架构审核、契约冻结或实施 Agent。
5. 只有用户明确点名具体方案/决策编号的回复，才可以将对应决策从 `awaiting-user-approval` 转换为 `user-approved`，并由根主线程写入 `docs/changes/<CHANGE_ID>/PRODUCT_APPROVAL.md`，原文记录用户回复、时间、批准范围和未批准范围。用户可以只批准部分决策；未覆盖的重大决策继续保持 `awaiting-user-approval`，不能把部分批准当作整个 Change 已批准。
6. 不得从沉默、Agent 推荐、技术可行性、历史相似决定、“继续”“推进”“ok”“确认”或无法识别具体选项的模糊回复推断批准。若用户回复未明确指向选项，继续保持 `awaiting-user-approval` 并重新询问。
7. 未批准方案只能保存在 change draft、候选产品文档和非约束性 feasibility/modeling 中；不得进入 `PRODUCT_ARCHITECTURE.md` 的有效架构部分、`TECH_ARCHITECTURE.md`、approved ADR、implementation-ready `TASKS.md` 或生产配置。

### 产品状态机与权限

唯一产品状态机为：

```text
draft
→ options-prepared
→ awaiting-user-approval
→ user-approved
→ product-baseline-updated
→ architecture-review
→ architecture-approved
→ implementation-ready
```

`product-agent` 只能推进准备阶段并设置 `awaiting-user-approval`；只有用户的明确回复可以把 `awaiting-user-approval` 转换为 `user-approved`。根主线程只负责记录用户决定，不得替用户选择。`architecture-agent` 在没有可核验的 `PRODUCT_APPROVAL.md` 前只能做非约束性的 feasibility/modeling，并必须返回 `blocked: awaiting-explicit-user-product-decision`；不得批准最终架构。普通 Agent 调度授权与系统安全审批分开处理。

## 2. 固定逻辑 Agent

当前项目只使用六个逻辑角色。物理 Worker 必须显式加载对应技能后才能承担该角色：

| 逻辑角色 | 技能文件 | 正式逻辑名称 | 主要职责 |
|---|---|---|---|
| `product-agent` | `agent-skills/product-agent/SKILL.md` | `product-agent-<nickname>` | 产品架构、需求、业务边界、产品变更记录 |
| `architecture-agent` | `agent-skills/architecture-agent/SKILL.md` | `architecture-agent-<nickname>` | 全局技术架构、影响分析、ADR、架构审批 |
| `backend-agent` | `agent-skills/backend-agent/SKILL.md` | `backend-agent-<nickname>` | 按批准架构实现后端 |
| `frontend-agent` | `agent-skills/frontend-agent/SKILL.md` | `frontend-agent-<nickname>` | 按批准架构实现 App/Admin |
| `qa-agent` | `agent-skills/qa-agent/SKILL.md` | `qa-agent-<nickname>` | 后端或前端独立 QA、架构符合性检查 |
| `e2e-agent` | `agent-skills/e2e-agent/SKILL.md` | `e2e-agent-<nickname>` | 完整用户旅程、跨模块和数据事实验收 |

- 不得创造 `*-agent-2`、`*-agent-new`、`helper-agent`、`specialist-agent` 等重复职责。
- `qa-agent` 是一个固定逻辑角色，但每个 QA 任务必须明确 scope 为 backend、frontend 或 cross-module；同一物理 Agent 不得兼任实现与 QA。
- 未加载角色技能的通用 Worker 不得修改产品架构、技术架构或业务代码。
- Agent 提示必须包含 Change/Feature ID、文档路径、文件所有权和必须保留的已有改动；详细需求只存在于仓库文档。
- 平台不支持修改面板 nickname 时，不得假称已重命名；项目记录只使用正式逻辑名称。

### Agent 运行实例、复用、授权与清理

- 本节构成适用于六个固定逻辑角色的持续调度授权，并取代更早会话或旧治理版本中的逐实例许可与禁止恢复要求。运行调度不得创建六个固定角色以外的新角色；如确需新增逻辑角色，必须先获得项目负责人明确授权并更新固定角色集合和对应技能，之后才能启动其实例。
- 启动、恢复或替换六个固定逻辑角色的运行实例不需要逐次申请；根主线程应在工作流门禁满足后自行调度，不得仅因当前没有 Agent 而停下询问用户。
- 调度优先级为：复用同角色仍可用的 thread → 恢复同角色已关闭的 thread → 自动启动同角色的替代运行实例。正确性不得依赖 thread 存活。
- 复用或恢复前必须确认任务兼容、重新读取仓库权威文档、重新声明任务范围与文件所有权；旧对话上下文不能替代仓库事实。
- 默认每个逻辑角色同时最多一个运行实例。同一角色不得并行启动重复实例；不同角色仍须遵守阶段门禁、文件所有权和共享契约不得并发编辑的限制。
- Agent 完成后先保存终态与交接证据。可以关闭实例以释放资源并保留其 ID 供以后恢复；关闭不表示该 thread 永久禁用。只有 thread 不可恢复、上下文不兼容或存在安全风险时才启动替代实例。
- 普通 Agent 调度授权与系统安全审批是两套独立机制。本节不豁免工具权限提升、敏感信息、破坏性操作、生产环境、外部写入或其他系统要求的审批，也不等同于创建用户拥有的新 Codex 任务。
- 固定角色实例的免申请调度不绕过产品、架构、契约、QA、人工审查、任务范围或文件所有权门禁。
- Agent 不设置固定单次执行时限。暂时无输出或无文件变化不构成失败。
- 根主线程只读监管运行中的 Agent，不催促、不插入补丁、不重复提醒。只有负责人要求、明确 blocked/failed、越权或破坏性行为时才停止。

## 3. 持久项目记忆

### 权威文档

| 事实 | 权威文件 |
|---|---|
| 当前完整产品架构 | `docs/product/PRODUCT_ARCHITECTURE.md` |
| 产品变更历史 | `docs/product/PRODUCT_CHANGELOG.md` |
| 当前完整技术架构 | `docs/architecture/TECH_ARCHITECTURE.md` |
| 技术架构变更历史 | `docs/architecture/ARCHITECTURE_CHANGELOG.md` |
| 重大技术决策及原因 | `docs/architecture/adr/ADR-XXX-title.md` |
| 后端职责边界 | `docs/backend/BACKEND_BOUNDARIES.md` |
| 前端职责边界 | `docs/frontend/FRONTEND_BOUNDARIES.md` |
| QA 策略与门禁 | `docs/qa/QA_STRATEGY.md` |
| C2/C3 影响分析与计划 | `docs/changes/CHG-YYYYMMDD-XXX.md` |
| 单功能需求与实现证据 | `docs/features/<FEATURE-ID>/` |

- 当前架构文档必须描述变更后的完整系统，不能只追加“本次新增”。
- Changelog 记录 WHAT；ADR 记录 WHY；Git 记录 EXACTLY WHAT CHANGED。
- 实现与文档不一致时，不得默认代码正确：先确认预期架构，再修代码或经架构审查更新文档。
- C2/C3 修改前记录当前 Git 状态。Git 不可靠或负责人明确要求时，才使用 `docs/*/history/` 文件备份，禁止 `v2-final-final` 风格副本。

### ADR 格式

重大架构决策使用 `docs/architecture/adr/ADR-XXX-title.md`，至少包含：

```text
Status
Context
Decision
Reason
Alternatives Considered
Rejected Alternatives
Consequences
Affected Modules
Date
Related Change ID
```

未来 Agent 在逆转已有决策前必须读取相关 ADR。

## 4. Change ID 与影响等级

- 重大变更编号：`CHG-YYYYMMDD-XXX`。
- Feature ID（如 `PAY-MP-001`）继续用于功能文档；C2/C3 同时创建 Change ID，并在影响分析、ADR、计划、changelog、QA 和提交信息中保持一致。

### C0 — 无架构影响

文案、颜色、间距、孤立小缺陷。可直接实现；无需 architecture-agent 或全局架构更新。

### C1 — 模块内部变化

责任仍位于现有模块内，如新增过滤、内部校验、单功能 UI 状态。必须检查模块边界并按需更新模块/feature 文档；通常无需 architecture-agent。

### C2 — 跨模块或契约变化

影响多个模块、API、事件或外部集成。强制要求：Change ID、影响分析、architecture-agent 审查、必要时更新完整技术架构、重大决策写 ADR。批准前不得实现。

### C3 — 核心架构变化

改变租户、身份、支付、OCPP、数据库或部署等基本假设。强制要求：产品架构审查、技术架构审查、当前状态版本记录、兼容性分析、ADR、迁移/回滚方案、实现计划、QA 与 E2E 计划。批准前不得实现。

## 5. 强制影响分析（C2/C3）

`docs/changes/<CHANGE_ID>.md` 必须明确回答：

1. 新能力还是已有能力修改？
2. 影响哪些产品域、技术模块和已有 owner？
3. 是否修改 API、数据库、业务规则、权限、租户、事件、外部集成或共享组件？
4. 应扩展现有模块、建立子模块、新领域，还是保持隔离？
5. 是否增加跨域耦合、循环依赖或隐藏依赖？
6. 是否保持向后兼容？是否需要迁移和回滚？
7. 变更后当前产品/技术架构是否仍准确？

标准结构：

```text
CHANGE_ID:
Requested Change:
Current Architecture:
Affected Product Domains:
Affected Technical Components:
Existing Owner Module:
Data Model Impact:
API Impact:
Permission Impact:
Tenant Impact:
Integration Impact:
Backward Compatibility:
Potential Coupling:
Circular Dependency Risk:
Migration Required:
Coupling Level: C0 | C1 | C2 | C3
Architecture Change Required: YES | NO
Recommended Integration Strategy:
Rejected Integration Strategies:
Reason:
Implementation Dependencies:
```

非 architecture-agent 发现架构冲突时不得静默重构，必须提交：

```text
ARCHITECTURE CHANGE REQUEST
Problem:
Current Architecture Constraint:
Observed Conflict:
Affected Modules:
Proposed Change:
Alternative:
Risk If Not Changed:
Suggested Coupling Level:
```

## 6. 标准工作流

### 6.1 支付接口治理规则

- 当前 App 支付接口统一使用 `POST/GET /api/v1/app/payments/checkout-sessions`、同一 Checkout Session 的 hosted checkout/confirm/query 子路径，以及 `/api/v1/app/payment-methods`。不得在 App 层新增或继续调用 `/create-<provider>`、`/pay-<provider>`、旧钱包支付创建或独立 PaymentOrder 状态接口。
- 当前产品只实现 Mercado Pago。Provider、收款主体、tenant/merchant、Access Token、佣金和 Provider-specific payload 均由服务端从可信业务事实解析，客户端不得提交或选择。
- Provider Webhook 是独立适配边界，统一进入 PaymentOrder/Checkout 状态机；当前 canonical 路径为 `/api/v1/app/payments/webhooks/mercadopago`，本地测试路径为 `/api/v1/app/payments/webhooks/sim`。Webhook 的验签、主动反查、字段映射和幂等逻辑只能位于对应 Provider Adapter/Webhook Adapter。
- 历史接口兼容不属于当前产品范围；旧接口移出当前路由注册，不新增数据库迁移、不导入或改写历史支付数据。源码中若暂时保留 legacy 实现，必须是未注册、不可被当前 App 调用的代码，并在文档中标明。
- 未来接入其他支付方式时，只能扩展 Provider Registry/Adapter、Credential Resolver、Provider Webhook Adapter、测试 fixture 和内部映射；不得改变 App Checkout Session 公共契约或复制一套 Provider 专属业务 API。

### 所有有意义变更

```text
Requirement
→ Read current product/technical architecture and relevant ADRs
→ Identify owner and perform impact analysis
→ Classify C0/C1/C2/C3
→ Version current state when C2/C3
→ Update product architecture when product shape changes
→ Architecture review and ADR when required
→ Freeze shared contract
→ Write implementation plan
→ Implement in dependency order
→ Independent QA
→ E2E when cross-module/user journey requires it
→ Update current architecture and changelogs
→ Human review
```

### C2/C3 实现计划

必须包含：

```text
CHANGE_ID
Goal
Approved Architecture
Affected Files / Modules
Database / API / Frontend / Backend Changes
Migration and Compatibility
Implementation Sequence
Tests and Regression Scope
E2E Scope
Rollback Strategy
```

跨层依赖顺序优先：架构 → 数据模型 → 共享契约 → 后端 → 前端 → QA → E2E。前后端不得各自发明不兼容契约。

## 7. Feature 文档与状态

正在开发的功能继续使用：

```text
docs/features/<FEATURE-ID>/
├── STATUS.md
├── product/{PRD.md,ACCEPTANCE.md,DECISIONS.md}
├── contracts/API.md
├── backend/{REQUIREMENTS.md,ARCHITECTURE_REVIEW.md,TECH_DESIGN.md,TASKS.md}
├── frontend/{REQUIREMENTS.md,ARCHITECTURE_REVIEW.md,TECH_DESIGN.md,TASKS.md}
└── qa/{BACKEND_QA_REPORT.md,FRONTEND_QA_REPORT.md,E2E_QA_REPORT.md}
```

- 模板位于 `docs/templates/feature/`；已完成旧需求可保留平铺结构，重新开发时再补齐新分层。
- `STATUS.md` 是功能流程状态入口，但不能替代全局产品/技术架构。
- 产品事实写 product；API 字段/状态/错误码只在 frozen contract；实现方案写技术文档；QA 报告只写独立证据。
- 产品、契约、架构、实现、QA、E2E 和人工审查未满足相应门禁时不得越级。

## 8. 角色启动协议

所有角色首先完整读取 `AGENTS.md`，并按职责读取：

- product-agent：产品架构、产品 changelog、相关 ADR/feature。
- architecture-agent：产品架构、技术架构、架构 changelog、相关 ADR/Change。
- backend-agent：技术架构、后端边界、相关 ADR、批准的 Change/feature/contract。
- frontend-agent：产品架构、技术架构、前端边界、相关 ADR、批准的 Change/feature/contract。
- qa-agent：产品架构、技术架构、QA strategy、批准计划、相关 ADR、实现交接与 diff。
- e2e-agent：产品架构、技术架构、QA strategy、前后端 QA 证据、相关 ADR 和完整旅程。

不得假设聊天上下文完整。

## 9. 文件所有权与任务收敛

- 每次只处理一个明确任务；Agent 开始后其任务文件为 `OWNER=agent`，同一文件同一时刻只有一个 owner。
- 根主线程在 Agent 运行期间只能只读监管，不得在其范围内准备、应用或试写补丁。
- Agent 结束后根主线程只读审查；发现缺陷按当前流程交回，不直接修改 Agent 交付。
- 主线程只有负责人明确说“接管”后才能获得业务实现文件所有权；接管前须确认 Agent 已终态并重新读取状态、目标文件和 diff。
- 不得以“顺便统一/重构”扩大范围。结构问题先评估是否需要 architecture change request。
- `apply_patch` 失败后必须重读文件，不得立即套用另一份大补丁。

## 9.1 强制自我修正循环

每个 Agent 必须持续验证当前工作仍与原始任务、批准范围、项目治理和当前架构一致。自我修正是强制的，但必须有界，不能演变为无限复读或扩展调查。

### SELF_CHECK 触发条件

以下时点必须执行一次 `SELF_CHECK`：

- 重大任务启动后 10 分钟内；
- 长时间审核期间每 10 分钟；
- 扩大任务范围前；
- 进入另一个审核域前；
- 重新读取已经审核过的文件前；
- 改变架构门禁前；
- 修改权威产品/技术架构文档前；
- 最终完成前。

### SELF_CHECK 内容

Agent 必须明确回答：

1. 原始任务的精确目标是什么？
2. 当前正在做什么？
3. 当前活动是否直接推进原始任务？
4. 自上次检查后产生了什么新证据、决策、产物或状态变化？
5. 是否在没有具体理由的情况下重读或重复评估已审核信息？
6. 是否超出分配的职责和文件范围？
7. 当前障碍属于：内部可解、缺少证据、治理冲突、架构冲突、外部依赖，还是需要用户决定？
8. 到达有效门禁结论所需的最小下一动作是什么？

### 强制纠正行为

- 发现 scope drift：立即停止扩展工作，返回原始范围，并把无关事项记为 TODO。
- 发现重复分析：停止重读，复用已有 review manifest、摘要和已验证证据。
- 发现治理冲突：不得发明有利于继续执行的解释；列出冲突。能够客观判断时执行高优先级规则，否则返回 `blocked` 并说明准确冲突。
- 缺少证据且阻止批准：立即返回 `changes-required` 或 `blocked`，列出准确证据，不得无限搜索。
- 需要用户决定：返回 `awaiting-user-approval` 并停止所有下游执行。
- 已有充分证据可以拒绝或阻塞：立即给出门禁结论，不为追求更完整而继续研究。

### 无进展检测和纠正预算

- 如果连续 10 分钟没有新的架构证据、产物、决策或门禁状态变化，必须记录 `SELF_CORRECTION_REASON: no-progress`，停止扩展调查，汇总现有证据和 blocker，并在 `continue-with-narrowed-scope`、`changes-required`、`blocked`、`awaiting-user-approval` 中选择一个，同时给出有界剩余计划。
- 每个任务最多执行两次重大自我修正。如果相同 blocker 在两次纠正后仍未解决，必须停止并返回当前证据支持的最佳门禁状态。

### 人工权限与完成标准

自我修正不得用于选择未决产品方案、批准商业或风险参数、发明支付限制、改变已批准产品行为、豁免安全控制、绕过用户批准，或把缺失用户决定解释为隐含批准；这些情况继续保持 `awaiting-user-approval`。

Agent 只有在最终交接中能够明确确认以下事项时，才算完成自我修正：原始范围已保留；无未解决的 scope drift；无重复分析循环；无隐藏治理冲突；剩余 blocker 已全部识别；当前 gate status 有证据支持；下一允许动作清晰。

## 10. QA 与完成门禁

qa-agent 必须同时验证功能正确和架构符合：

- 产品架构、技术架构、模块边界和 ADR 是否遵守；
- API/事件契约、权限、租户隔离和向后兼容是否保持；
- 后端 scope 覆盖 API、服务、数据库、Redis/队列/Webhook/OCPP、审计和脏数据；
- 前端 scope 覆盖构建/类型、导航、API 映射、共享组件、加载/空/错误/恢复、本地化、可访问性和相邻流程；
- QA 不得通过修改产品代码让测试通过，未知数据状态不得判 pass。

e2e-agent 只在相关 QA 通过后介入，必须从用户角度验证完整旅程，并核对 UI、API、数据库、异步状态、权限和租户事实。

C2/C3 完成至少要求：

1. 需求已实现；
2. 当前产品架构一致；
3. 当前技术架构一致；
4. 相关 ADR 和 changelog 完成；
5. 模块边界与契约保持；
6. 测试和回归通过；
7. 适用时 E2E 通过；
8. 不存在未记录的架构偏差；
9. 人工审查完成。

测试未完成或发现新问题时先报告，不自动扩大为修复任务。没有证据不得声称“完全通过”。

### 10.1 Sandbox QA 预授权

- `qa-agent` 和 `e2e-agent` 对已批准的本地/测试 Sandbox 支付链路拥有持续执行授权；执行该范围内的浏览器操作、官方测试账号登录、官方测试卡提交、测试 Webhook 验证和测试数据核对，不需要逐次向产品负责人申请或等待再次确认。
- 该预授权仅覆盖 `ENVIRONMENT=test` 或本地测试 Compose、Provider Sandbox、官方测试账号/测试卡和不产生真实资金转移的测试金额；不得扩展到生产环境、生产凭证、真实银行卡、真实退款、生产 Webhook 或生产数据库。
- Sandbox QA 仍必须遵守环境/Compose 硬规则、支付接口治理、租户隔离、日志清洗、幂等和审计要求，并在 QA 证据中记录测试路径、订单/会话/Provider 事实和最终状态。
- 本条是产品 QA 的预授权，不替代系统安全审批、工具权限提升或平台对真实资金和敏感数据的强制安全门禁；发现目标环境不一致时仍必须 `blocked: environment-mismatch`，不得自行切换环境或新建配置。

## 11. 安全与领域约束

- 不部署生产环境，不操作生产数据库。
- 不提交密码、Token、证书、私钥或真实支付凭证。
- 所有业务数据考虑 `tenant_id` 和多租户隔离；后端不能信任前端传入的 `tenant_id` 作为最终授权依据。
- App 可查看公开充电资源；后台交易、账务和结算必须按租户隔离。
- 金额不得使用二进制浮点；后端时间统一存 UTC。
- 设备事件、支付回调、远程指令必须幂等；充电会话和支付使用明确状态机并校验迁移。
- 关键运营操作必须有审计日志；不得擅自假设 OCPP 或设备协议版本。
- 当前支付功能全部 QA 和人工审查完成前，生产 `PAYMENT_RAILS_ENABLED` 必须保持 `false`。

## 12. 工作区与工具

- 工作区可能包含负责人未提交改动；必须保留，不得回退或清理无关内容。
- 禁止 `git reset --hard`、`git checkout --` 等破坏性命令，除非负责人明确要求。
- 文件编辑优先使用 `apply_patch`；搜索优先 `rg`/`rg --files`。
- 先看限定 `git diff --stat`/diff，再读具体补丁；不重复读取未变化文件。
- 多个问题统一修复后再构建，避免每个问题重复构建。

## 12.1 环境与 Compose 硬性治理

以下规则是项目级硬规则，适用于所有 Agent、脚本、开发者和测试任务：

1. 测试环境不得随意创建新的环境文件。测试配置只能使用既有的 `.env.test.local`、`.env.example` 中的测试模板和当前批准的环境注入方式。确需新增环境文件时，必须先提交 `ENVIRONMENT CHANGE REQUEST`，说明用途、变量清单、读取方、生命周期、密钥存储方式和回滚方案，并等待产品负责人明确批准。
2. 不得随意创建新的 `docker-compose*.yml` 文件。必须优先复用本项目已登记的 Compose 入口；新增入口或复制现有入口均须先提交 `COMPOSE CHANGE REQUEST`，说明不能复用的具体原因、服务差异、端口/卷/网络影响和清理计划，并等待人工确认。
3. 不得随意更改既有环境文件、Compose 文件、环境变量名称、默认值、服务映射、端口、卷、网络、依赖、健康检查或构建参数。涉及这些内容的修改必须记录变更 ID、目标环境、影响分析、验证命令和回滚方式；支付、认证、Webhook、数据库或生产相关配置必须经过相应架构/安全门禁。
4. Compose 和配置文件的选择必须遵守 `docs/deployment/ENVIRONMENT_AND_COMPOSE_GOVERNANCE.md`。不得通过文件名猜测环境，不得把一个环境的 Compose 与另一个环境的 env 文件混用；命令中必须显式写出环境文件和 Compose 文件（仅默认开发栈可使用无 `-f` 的兼容命令）。
5. 前端、后端、模拟器和 QA 必须使用同一个目标环境标识、同一套 Compose 栈、同一套 API/WS 地址和同一份测试数据基线。若出现 `ENVIRONMENT`、端口、API URL、Webhook URL、Provider 模式或数据卷不一致，状态必须为 `blocked: environment-mismatch`，不得通过临时覆盖、额外 env 文件或临时 Compose 绕过。
6. 任何环境/Compose 阻塞项都必须保留现状并向产品负责人进行人工询问。Agent 不得自行选择替代环境、临时复制配置、隐式切换 Compose、修改支付开关或把“能启动”解释为环境一致。
7. 仅允许在本地/测试范围内使用测试密钥；Access Token、Webhook Secret、卡数据和账户密码必须通过已批准的本地忽略文件或 secret provider 注入，不得写入 Git、权威架构文档、Notion、Compose 明文默认值或前端构建产物。

## 13. 统一交接格式

```text
STATUS: done | blocked | failed

CHANGED_FILES:
- files

COMMANDS_RUN:
- commands

TEST_RESULTS:
- exact results

CONTRACT_CHANGES:
- API / public types / database / events

ARCHITECTURE_COMPLIANCE:
- coupling level, ADR, boundaries, drift

RISKS:
- remaining risks and decisions required
```

## 14. Deterministic orchestration runtime

Agent 编排的运行时事实不依赖聊天记录或自然语言推断，统一持久化在：

- `.codex/runtime/agents.json`：逻辑角色到 `runtime_agent_id`、thread、任务、状态和终态结果的 Registry；
- `.codex/runtime/orchestrator-state.json`：当前 workflow、阶段、监控、收敛、QA、阻塞和主线程停止门禁；
- `.codex/hooks.json`：项目级 `Stop` 与 `SubagentStop` Hook，入口为 `.codex/runtime/orchestrator.py`。

强制规则：

- Agent 启动协议是原子的两步门禁：`multi_agent_v1__spawn_agent` 返回后，必须立即用返回的 `agent_id` 执行 `python3 .codex/runtime/orchestrator.py register-agent ...`，成功写入 Registry 后才能发送任务、poll、status 或 wait。`agent_id` 是 `runtime_agent_id`；`send_input` 返回的 `submission_id` 永远不是 Agent ID，禁止登记或轮询它。注册失败时不得继续等待，必须保持主线程 Stop blocked 并报告 runtime blocker；
- 启动 Agent 后 Registry 必须立即出现 `pending_init` 记录及 `active_agents`/`pending_agents` 投影；后续 poll/status/resume/recovery 只能通过 Registry 解析真实 `runtime_agent_id`，不得从聊天文本或消息 submission ID 推断；
- `POLL_INTERVAL_EXPIRED` 只表示轮询窗口结束，绝不表示 Agent completed/failed/cancelled 或允许主线程结束；超时后必须 checkpoint、convergence check 并继续 poll；
- `allow_main_thread_stop` 默认必须为 `false`。Stop Hook 每次运行都必须从 Registry 和 workflow state 重新计算所有收敛条件，不能信任缓存的 `allow_main_thread_stop=true`；只有所有 mandatory Agent 为 terminal、收敛检查完成、阶段 gate 有正式状态、无待处理结果、无用户审批等待且没有必须继续的阶段时，Stop Hook 才能 allow；
- `SubagentStop` 必须检查 scope、self-check、convergence、verification、scope drift 和 terminal result；缺项只能 block 并要求 focused correction pass；
- 运行超过 10 分钟的 Agent 每 10 分钟写 monitoring checkpoint；连续两个无 meaningful progress 触发 self-correction，最多两轮，仍不收敛则记录 blocked/changes-required；
- AGENTS.md 或其他治理文件改变后，旧 Agent 不得假定已自动 reload。新 Agent 使用新 hash；运行 Agent 必须显式完成 governance reload acknowledgement，必要时在安全 checkpoint 后恢复；
- 主线程提前返回后，恢复流程只复用 Registry 中的原 Agent，不创建重复实例。

实现和模拟验证见 `.codex/runtime/orchestrator.py` 与 `.codex/runtime/test_orchestrator.py`。这些文件只属于 Agent orchestration/governance 基础设施，不得承载业务逻辑。
