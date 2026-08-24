---
id: ALERT-I18N-001
status: ready-for-execution
scope: P0
owner: qa_engineer
contract: docs/features/ALERT-I18N-001/API_CHANGES.md
---

# 告警可读性与国际化测试计划

## 1. 目标与准入

验证运营人员可在中文、英文和西班牙语下准确识别并处理告警，且告警资产上下文严格受租户隔离保护，内部 UUID 不进入运营界面。

执行验收前必须满足：

- 后端、前端实现及开发侧自动化测试已完成，API 契约仍为 `contract: frozen`。
- 测试环境可创建两个独立租户及对应站点、充电桩、EVSE、管理员和告警。
- 可切换 `zh`、`en`、`es` 三种语言，并可访问站点及设备管理详情页。
- 本计划不包含高级筛选、历史时间线、批量处理或告警规则编辑。

## 2. 测试数据

| 数据 | 租户 | 资产关系 | 告警代码/状态 | 用途 |
| --- | --- | --- | --- | --- |
| A1 | Tenant A | Site A / CP A / EVSE A | `charger.offline.heartbeat_timeout` / pending | 完整上下文、参数插值、确认与解决 |
| A2 | Tenant A | Site A / CP A / EVSE A | `charger.offline.websocket_disconnected` / acknowledged | 已确认后解决、原始技术信息 |
| A3 | Tenant A | Site A / CP A / EVSE A | `charger.faulted` / resolved | 已解决不可重复处理 |
| A4 | Tenant A | Site A / CP A / EVSE A | `device.event` / pending | 设备事件本地化 |
| A5 | Tenant A | 无关联 | `manual` / pending | 三个关联对象均为空 |
| A6 | Tenant A | 分别缺 Site、CP 或 EVSE | 各 P0 代码 | 部分空关联组合 |
| A7 | Tenant A | Site A / CP A / EVSE A | 未知代码 / pending | 通用本地化回退及原文保留 |
| B1 | Tenant B | Site B / CP B / EVSE B | 任一 P0 代码 / pending | 跨租户读取、处理和关系污染测试 |

所有内部主键使用可识别的 UUID 测试值；站点、设备及 EVSE 同时准备与 UUID 不相似的运营标识（`site_code`、`ocpp_identity`、数字 `evse_id`/`physical_reference`），以便检测误展示。`raw_message` 使用明确英文技术文本，`message_params.timeout_seconds` 使用 `90`，并准备包含缺失和额外参数的负向样本。

## 3. 自动化覆盖矩阵

### 3.1 API 与租户隔离

| ID | 场景与步骤 | 预期结果 | 建议层级 |
| --- | --- | --- | --- |
| API-01 | Tenant A 调用 `GET /api/v1/admin/alerts`，读取完整关联告警 | 保留既有字段；新增 `alert_code`、对象型 `message_params`、可空 `raw_message`、`site`、`charge_point`、`evse`；字段类型和冻结契约一致 | API 自动化 |
| API-02 | 对 list、create、detail、acknowledge、resolve 等所有声明返回 `AlertResponse` 的端点分别取响应 | 每个端点均返回同一结构化契约，新增字段不会只出现在列表；既有字段无破坏性删除或改型 | API 契约自动化 |
| API-03 | 分别创建/读取五个 P0 `alert_code` | 稳定返回文档列出的五个代码；参数位于 `message_params`，主文案不依赖后端语言 | API 参数化自动化 |
| API-04 | 读取未知 `alert_code` 和含英文 `raw_message` 的告警 | 未知代码原样返回，`raw_message` 不丢失，API 不报错 | API 自动化 |
| API-05 | 读取无关联及部分关联告警 | `site`、`charge_point`、`evse` 均允许独立为 `null`；响应成功且其余字段完整 | API 参数化自动化 |
| API-06 | Tenant A 列表、筛选及详情读取 | 只返回 Tenant A 告警；Tenant B 告警 ID 的详情请求返回 404 或等价的不泄露响应 | API 安全自动化 |
| API-07 | Tenant A 使用 Tenant B 的充电桩引用筛选或创建告警 | 不能解析、返回或关联 Tenant B 资产，响应不泄露资产是否存在 | API 安全自动化 |
| API-08 | 构造“Tenant A 告警错误关联 Tenant B 的 Site/CP/EVSE”的数据并读取 | 关联上下文必须按当前租户再次约束；不得返回 Tenant B 的名称、地址、OCPP Identity、型号、序列号、EVSE 编号或物理位置 | API 安全自动化 |
| API-09 | Tenant A 对 Tenant B 告警调用 acknowledge/resolve | 返回 404 或等价的不泄露响应；B1 状态、时间及操作者均未改变 | API 安全自动化 |
| API-10 | pending 告警执行 acknowledge，再执行 resolve | 状态依次为 acknowledged、resolved，时间字段按状态更新；响应继续满足完整 `AlertResponse` 契约 | API 状态自动化 |
| API-11 | 对 resolved 告警再次 acknowledge 或 resolve | 操作被拒绝或保持幂等且不产生新的状态变更；不得重新开放告警 | API 状态自动化 |

API 契约断言应显式验证：

- `site` 为 `null` 或包含 `site_code`、`name`、`address`。
- `charge_point` 为 `null` 或包含 `ocpp_identity`、`model`、`serial_number`。
- `evse` 为 `null` 或包含数字 `evse_id`、可空 `physical_reference`。
- `charge_point_id`、内部 `evse_id` 等既有关系字段允许继续返回给客户端，但只能用于内部关联，不能成为主界面文案或跳转标识。
- 无租户上下文时拒绝请求；授权依据来自认证租户上下文，而不是请求体或查询参数中的 `tenant_id`。

### 3.2 三语言、空关联与展示边界

以下组件/集成用例对 `zh`、`en`、`es` 参数化执行；每次切换语言后在同一数据集上重新断言，避免仅测试初始语言。

| ID | 场景与步骤 | 预期结果 | 建议层级 |
| --- | --- | --- | --- |
| UI-01 | 展示五个 P0 代码，覆盖参数插值 | 主标题和主描述均为当前语言，参数值正确插入；不混入其他两种语言或后端旧 `title`/`description` | 组件自动化 |
| UI-02 | 展示 critical、warning、info 及 pending、acknowledged、resolved | 严重程度和状态标签完整本地化，不直接显示英文枚举值 | 组件自动化 |
| UI-03 | 在页面内依次切换 `zh`、`en`、`es` | 已加载告警立即使用目标语言重渲染；标题、描述、严重程度、状态、空值标签和操作按钮保持同一语言 | 集成自动化 |
| UI-04 | 展示 A1 完整资产上下文 | 紧凑列表可识别站点名称、OCPP Identity 和 EVSE 编号；可在详情看到契约允许的辅助资产信息 | 组件自动化 |
| UI-05 | 参数化展示 A5/A6 的全空及各单项缺失组合 | 每个缺失位置显示对应语言的“未关联”，页面不崩溃、不出现 `undefined`、`null`、空白占位或错误链接 | 组件自动化 |
| UI-06 | 将告警、充电桩、EVSE 及 tenant 的内部 UUID 放入 API fixture | 主列表、展开详情、按钮文案、链接文本、链接目标、可访问名称及提示中均不出现内部 UUID；显示运营标识 | 组件/集成自动化 |
| UI-07 | A1/A2 带英文 `raw_message`，初始渲染列表 | 原始英文技术文本不出现在主标题、主描述或默认折叠内容中 | 组件自动化 |
| UI-08 | 展开技术详情后再收起 | 仅展开时显示完整、未本地化篡改的 `raw_message`；收起后不可见；空 `raw_message` 不显示误导性内容 | 组件自动化 |
| UI-09 | 展示未知 `alert_code` | 使用当前语言的通用标题和描述，不显示代码作为业务文案；技术详情仍保留 `raw_message` | 组件自动化 |
| UI-10 | 搜索或刷新后复查告警卡片/行 | 本地化、资产上下文、折叠状态和 UUID 隐藏边界不因列表重渲染而失效 | 集成自动化 |

三语言断言使用固定期望文案或稳定翻译 key，不采用“文本存在即可”的弱断言。UUID 隐藏用例应针对已知 fixture UUID 做否定断言，并对页面可见文本和生成的 `href` 同时检查。

### 3.3 跳转、确认与解决

| ID | 场景与步骤 | 预期结果 | 建议层级 |
| --- | --- | --- | --- |
| NAV-01 | 点击 A1 的“查看站点” | 跳转到 Site A 管理详情，使用 `site_code` 对应的安全路由参数；页面显示 Site A，URL 和可见文本不含站点内部 UUID | 集成/E2E |
| NAV-02 | 点击 A1 的“查看设备” | 跳转到 CP A 管理详情，使用 `ocpp_identity` 对应的安全路由参数；页面显示 CP A，URL 和可见文本不含充电桩内部 UUID | 集成/E2E |
| NAV-03 | 站点或设备为空时检查操作区 | 对应查看按钮不提供可点击的无效链接，仍显示本地化“未关联”，无控制台异常 | 组件/E2E |
| ACT-01 | pending 告警点击确认并等待刷新 | 仅发出一次 acknowledge 请求；成功反馈本地化，状态变为 acknowledged，确认按钮消失，解决按钮保留 | 集成/E2E |
| ACT-02 | pending 告警直接解决，或 acknowledged 告警点击解决 | 仅发出一次 resolve 请求；成功反馈本地化，状态变为 resolved，所有处理按钮消失 | 集成/E2E |
| ACT-03 | 打开 resolved 告警 | 不呈现可触发 acknowledge/resolve 的按钮或快捷操作，刷新后仍不可重复处理 | 组件/E2E |
| ACT-04 | acknowledge/resolve 返回 4xx/5xx | 显示当前语言的失败反馈，状态和按钮保持原状，不产生乐观误报 | 集成自动化 |
| ACT-05 | 无 `alerts.write` 权限的用户打开列表 | 可读用户不能看到或触发确认/解决；有权限用户行为不受影响 | 集成自动化 |

## 4. 真实页面验收

在支持的桌面视口上对三种语言各执行一轮，至少包含 A1、A5、A7：

1. 打开告警管理页，确认紧凑列表在首屏可识别告警类型、严重程度、状态、站点、OCPP Identity 和 EVSE 编号。
2. 切换三种语言，逐项检查主标题、主描述、严重程度、状态、“未关联”、技术详情、跳转及操作文案无语言混杂。
3. 检查默认视图不暴露任何已知内部 UUID；展开技术详情后仍不把 UUID 当作业务标识。
4. 展开 A1/A7 技术详情，确认原始技术信息完整且只在该区域出现。
5. 分别执行站点和设备跳转，核对落地资产与原告警上下文一致，并使用安全外部标识。
6. 完成 pending -> acknowledged -> resolved 操作，刷新页面确认状态持久化且 resolved 不可重复处理。
7. 用 Tenant B 登录并复查列表、详情 URL、操作端点，确认 Tenant A 告警及资产上下文不可见、不可处理。

真实页面检查同时记录浏览器控制台错误、失败网络请求及截图；发现缺陷时保留语言、租户、告警代码、状态和关联组合信息。

## 5. 回归与出场标准

最小回归范围：告警列表加载/搜索/状态及严重程度筛选、告警权限控制、站点详情、设备详情、语言切换，以及既有 AlertResponse 客户端消费路径。只运行直接相关的 API、组件、集成和 E2E 测试，不在本任务中执行容器构建或全量回归。

P0 出场条件：

- API-01 至 API-11、UI-01 至 UI-10、NAV-01 至 NAV-03、ACT-01 至 ACT-05 全部通过。
- 三语言、API 契约和空值场景均有可重复自动化证据。
- 无跨租户数据泄漏、内部 UUID 展示、原始技术文本进入主文案、错误资产跳转或已解决告警重复处理。
- 真实页面三语言与双租户验收完成，无未关闭 P0/P1 缺陷。
- 若冻结 API 契约需要变化，停止验收并由产品/后端更新正式契约后重新评审，不以测试适配代替契约确认。
