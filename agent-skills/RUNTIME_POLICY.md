# Fixed Logical Agent Runtime Policy

本文件是六个固定逻辑角色共同使用的运行实例策略；角色职责仍以根 `AGENTS.md` 和各角色 `SKILL.md` 为准。

1. 固定逻辑角色只有：`product-agent`、`architecture-agent`、`backend-agent`、`frontend-agent`、`qa-agent`、`e2e-agent`。
2. 运行调度不得创建上述六个固定角色以外的新角色。新增逻辑角色、改变固定角色集合或扩大角色职责必须先由项目负责人明确授权并更新治理与角色技能，之后才能启动其实例。
3. 启动、恢复或替换固定角色的运行实例无需逐次向用户申请；当前没有可用 Agent 也不是暂停询问的理由。
4. 调度顺序是：复用同角色可用 thread → 恢复同角色已关闭 thread → 自动启动同角色替代实例。
5. 默认每个逻辑角色同时最多一个运行实例；不得为同一角色并行创建重复实例。
6. 完成后保存终态和交接证据。实例可关闭以释放资源，并可在后续任务中恢复；关闭不代表永久禁用。
7. 复用或恢复时必须重新加载权威文档、任务范围和文件所有权，不能把旧聊天上下文当作项目事实。
8. 普通 Agent 调度授权不豁免系统安全审批、工具权限提升、生产操作、破坏性操作、敏感信息处理或外部写入审批。
9. 固定角色调度授权不绕过产品、架构、契约、实现、QA、E2E、人工审查和文件所有权门禁。

## Registry-first launch protocol

`multi_agent_v1__spawn_agent` 返回后，根主线程必须立即把返回的 `agent_id` 作为
`runtime_agent_id` 写入 `.codex/runtime/agents.json`，再发送任务或执行任何
wait/status/resume。`send_input` 返回的 `submission_id` 不是 Agent ID，禁止写入
Registry。注册失败时不得继续等待；必须保持 Stop Hook blocked 并报告 runtime
blocker。Stop Hook 每次都从 Registry 和 workflow state 重新计算收敛条件，不能信任
缓存的 `allow_main_thread_stop`。

## Mandatory Self-Correction Loop

1. 每个固定角色必须在重大任务启动后 10 分钟内、长审核每 10 分钟、扩大范围前、切换审核域前、重读已审文件前、改变架构门禁前、修改权威架构文档前及最终完成前执行 `SELF_CHECK`。
2. `SELF_CHECK` 必须回答：原始任务、当前活动、是否直接推进、新证据/产物/状态、是否重复读取、是否扩 scope、障碍分类、最小下一动作。
3. scope drift 时停止扩展并记录 TODO；重复分析时停止重读并复用 review manifest/摘要；治理冲突无法按优先级客观解决时返回 `blocked`；证据不足时返回 `changes-required` 或 `blocked`；需要用户决定时返回 `awaiting-user-approval` 并停止下游执行。
4. 连续 10 分钟无新证据、产物、决策或 gate change 时记录 `SELF_CORRECTION_REASON: no-progress`，停止扩展调查并选择 `continue-with-narrowed-scope`、`changes-required`、`blocked` 或 `awaiting-user-approval`，附有界计划。
5. 每个任务最多两次重大自我修正；同一 blocker 两次未解后必须停止并返回最佳证据支持的 gate status。
6. 自我修正不得替代产品选择、商业/风险参数、支付限制、安全控制或用户批准，也不得修改已批准行为。
7. 最终交接必须明确：original scope preserved、no unresolved scope drift、no repeated analysis loop、no hidden governance conflict、all remaining blockers identified、gate justified、next allowed action defined。

## Human Product Decision Gate

1. `product-agent` 可以分析、提出候选方案和推荐，但不得替用户选择；推荐不等于批准。
2. 重大产品决策必须生成 `docs/changes/<CHANGE_ID>/PRODUCT_DECISION_REQUEST.md`，状态设为 `awaiting-user-approval`，并在输出后停止。
3. 根主线程收到该状态后必须向用户询问具体选项；不得从沉默、推荐、技术可行性、历史决定、“继续/推进/ok/确认”或模糊回复推断批准，也不得继续调度最终架构审核或实施 Agent。
4. 只有用户明确指向具体方案/决策编号的回复，且已写入 `PRODUCT_APPROVAL.md`，对应决策才可进入 `user-approved`。部分批准不等于整个 Change 已批准；仍有重大决策未覆盖时，整体继续保持 `awaiting-user-approval`，不得进行最终架构审核或冻结实现门禁。
5. `architecture-agent` 在缺少明确 `PRODUCT_APPROVAL.md` 时只能进行非约束性 feasibility/modeling，并必须返回 `blocked: awaiting-explicit-user-product-decision`；不得批准最终架构。

产品状态机固定为：`draft → options-prepared → awaiting-user-approval → user-approved → product-baseline-updated → architecture-review → architecture-approved → implementation-ready`。

本策略按项目负责人 2026-08-12 的最新授权生效，并取代更早会话或旧治理版本中的逐实例许可与禁止恢复要求。
