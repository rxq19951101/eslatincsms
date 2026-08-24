# EsLatin App 产品交互与页面流程

> 文档类型：前端 App 产品文档（页面与交互逻辑）
> 文档状态：`CURRENT_AS_IS` 只描述当前已定义/已实现的产品行为，不代表所有上线门禁均已通过。
> 维护角色：product-agent
> 基线日期：2026-08-24
> 关联权威文档：`docs/product/PRODUCT_ARCHITECTURE.md`

## 1. 文档目的

本文档把 EsLatin App 的用户旅程拆解为“页面 → 用户操作 → 服务端事实 → 下一页面 → 异常恢复”的完整产品链路，供产品、前端、后端、QA 和人工验收共同使用。

本文档回答以下问题：

- 用户在每个步骤看到什么页面和关键信息；
- 用户可以点击什么、什么时候不能点击；
- 页面动作对应的产品意图和服务端状态是什么；
- 成功、处理中、失败、过期、离线和返回时如何继续；
- 充值、直接刷卡充电、钱包充电、保存银行卡和欠费补缴如何区分；
- 页面显示的状态如何与充电桩、Checkout、Invoice、Payment 和钱包事实对应。

本文档不是前端技术设计，也不替代 API 契约。接口字段和错误码以对应 frozen contract 为准；技术实现以 `docs/architecture/TECH_ARCHITECTURE.md` 和 feature 技术文档为准。

## 2. 阅读约定

| 标记 | 含义 |
|---|---|
| 页面 | 用户当前可见的 App 页面或页面状态 |
| 用户动作 | 点击、输入、返回、刷新、扫码或等待 |
| 服务端事实 | 必须由后端/Provider/OCPP/数据库确认的状态 |
| 下一页面 | 成功或安全恢复后的导航目标 |
| 可恢复异常 | 用户可以重试、返回或进入支持的状态 |
| 阻断异常 | 不允许继续业务动作，必须先满足前置条件 |
| 当前行为 | 当前产品已定义的 As-Is 行为 |
| 待验收 | 已有产品定义，但仍需 QA、Provider 或生产门禁证据；不能当作已上线承诺 |

页面文案以西班牙语为首要用户语言；中文/英语属于语言设置支持范围。状态不能只靠颜色表达，必须同时有文字、可操作动作或明确的不可操作原因。

## 3. App 信息架构与页面地图

### 3.1 页面分组

| 产品域 | 页面/路由 | 主要目的 |
|---|---|---|
| 身份 | `Welcome`、`EmailLogin`、`EmailRegister`、`EmailVerification`、`VerificationSuccess`、`ForgotPassword`、`ResetPassword` | 注册、登录、验证和密码恢复 |
| 首次使用 | `LocationPermission` | 请求位置权限并解释用途 |
| 主导航 | `MainTabs` | 承载首页、收藏、扫码、钱包、账户五个主入口 |
| 发现 | `Home`、`StationDetail`、`Saved` | 查找站点、查看充电资源和收藏 |
| 扫码 | `Scan` | 相机扫码或手动输入充电桩 QR token |
| 充电 | `ChargingProcess`、`ChargingComplete` | 选择结算方式、启动、监控、停止和查看最终结算 |
| 历史 | `ChargingHistory`、`ChargingHistoryDetail` | 查看充电事实、金额、支付状态和支持入口 |
| 支付 | `PaymentHub`、`PaymentMethods`、`AddPayment`、`PaymentResult`、`MercadoPagoPayment` | 钱包、银行卡、托管 Checkout 和支付结果恢复 |
| 欠费恢复 | `UnpaidBills`、`UnpaidBillDetail` | 查看阻断性未结账单、补缴和进入支持 |
| 账户 | `Account`、`PersonalInfo`、`Language` | 账户资料、语言、支付和服务入口 |
| 支持与法律 | `SupportCases`、`SupportCaseDetail`、`HelpCenter`、`PrivacyPolicy`、`About` | 工单、帮助、隐私和关于 |

### 3.2 主充电旅程

```mermaid
flowchart TD
    A[Welcome] --> B{已有账户?}
    B -- 否 --> C[EmailRegister]
    C --> D[EmailVerification]
    D --> E[VerificationSuccess]
    B -- 是 --> F[EmailLogin]
    E --> G[LocationPermission]
    F --> G
    G --> H[MainTabs / Home]
    H --> I[StationDetail]
    I --> J[MainTabs / Scan]
    J --> K[ChargingProcess: checking]
    K --> L{充电桩状态}
    L -- offline --> L1[离线页面: 重试/返回]
    L -- charging_other --> L2[使用中页面: 重试/返回]
    L -- available --> M{选择结算方式}
    M -- 钱包 --> N[服务端 preflight]
    N --> O[启动充电]
    M -- 新卡/保存卡 --> P[Checkout Session 托管页]
    P --> Q[PaymentResult]
    Q -- ready --> R[返回原充电桩 ChargingProcess]
    R --> O
    Q -- approved/top-up --> S[按支付目的跳转]
    O --> T[ChargingProcess: charging_self]
    T --> U[MeterValues/实时状态]
    U --> V[停止或设备停止]
    V --> W[ChargingComplete]
    W --> X{最终资金状态}
    X -- paid --> Y[历史/首页]
    X -- unpaid/processing --> Z[UnpaidBill 或支持入口]
```

### 3.3 支付目的分流

同一个托管 Checkout 结果页必须根据服务端保存的 `purpose` 恢复到正确业务上下文，不根据用户当前猜测或客户端金额判断。

| 支付目的 | 触发页面 | 完成后的下一步 |
|---|---|---|
| `charging_direct` | `ChargingProcess` 选择新卡/保存卡 | `PaymentResult` 显示 ready 后回到同一个充电桩，再由用户明确点击开始充电 |
| `wallet_top_up` | `PaymentHub` 或钱包充值入口 | `PaymentResult` 成功后回到 `MyWallet`，确认钱包只增加一次 |
| `save_card` | `AddPayment` | `PaymentResult` 成功后回到 `PaymentMethods`，只展示非敏感卡片摘要 |
| `unpaid_charge` | `UnpaidBills`/`UnpaidBillDetail` | `PaymentResult` 收敛后回到账单上下文，只有服务端确认足额结清才解除阻断 |

`MercadoPagoPayment` 是当前保留的支付兼容页面入口，当前产品主要用途是钱包充值；新增 App 支付不得再复制 Provider 专属创建接口或独立支付订单流程。

### 3.4 UI 截图与交互步骤的对应关系

真实 UI 截图不单独作为设计素材展示，而是直接嵌入第 4 节对应页面的交互表中。截图来自本地测试 App `http://localhost:8081`，不是线框图或 AI 生成图。图片文件位于 `docs/product/app-ui/`，仅作为 Markdown 的渲染资源。

截图中的站点、账户、余额和交易属于本地测试数据；它们用于说明页面实际形态，不代表产品默认数据，也不能替代浏览器交互 QA、API/数据库事实核对或生产发布门禁。充电启动前的截图以当前本地 OCPP 测试夹具实际返回的状态为准；当前夹具未提供可复现的 `checking`、`charging_other` 和已在线可充电流程时，文档会嵌入实际的阻断/入口截图并在表格中标明状态，不把其他页面冒充成目标状态。

## 4. 页面与交互目录

### 4.1 身份与首次进入

| 步骤 | 页面 | 页面展示 | 用户动作 | 服务端/系统逻辑 | 下一步与异常 | UI截图 |
|---|---|---|---|---|---|---|
| AUTH-01 | `Welcome` | 品牌、登录、注册入口 | 点击登录或注册 | 仅做导航，不创建支付/充电事实 | 登录 → `EmailLogin`；注册 → `EmailRegister` | ![Welcome](app-ui/01-welcome.png) |
| AUTH-02 | `EmailLogin` | 邮箱、密码、记住我、忘记密码 | 提交登录 | 服务端验证身份、租户/受众和会话 | 成功 → `MainTabs` 或位置权限；错误 → 可行动错误，保留输入并允许重试 | ![登录](app-ui/10-email-login.png) |
| AUTH-03 | `EmailRegister` | 邮箱、密码和注册字段 | 提交注册 | 创建待验证账户并发送验证流程 | 成功 → `EmailVerification`；重复/非法输入 → 字段级错误 | ![注册](app-ui/11-email-register.png) |
| AUTH-04 | `EmailVerification` | 验证码输入、重新发送和倒计时 | 输入验证码/重发 | 服务端确认验证码，不把未验证账户视为已登录 | 成功 → `VerificationSuccess`；失败 → 错误与重试 | ![邮箱验证](app-ui/12-email-verification.png) |
| AUTH-05 | `VerificationSuccess` | 注册成功和继续入口 | 继续进入 App | 建立已验证身份上下文 | → `LocationPermission` 或 `MainTabs` | ![验证成功](app-ui/13-verification-success.png) |
| AUTH-06 | `ForgotPassword` | 邮箱输入和发送入口 | 请求重置邮件 | 服务端发出重置流程，不泄露账号是否存在 | 成功显示统一提示；失败可重试 | ![忘记密码](app-ui/14-forgot-password.png) |
| AUTH-07 | `ResetPassword` | 新密码、确认密码 | 提交新密码 | 验证重置 token、更新密码、使旧 token 失效 | 成功 → `EmailLogin`；过期/无效 → 重新请求 | ![重置密码](app-ui/15-reset-password.png) |
| AUTH-08 | `LocationPermission` | 为什么需要定位、允许/稍后处理 | 授予或拒绝 | 记录本机权限状态；拒绝不应阻断查看公开站点 | 授予/跳过 → `MainTabs`；错误 → 仍可手动刷新/查看列表 | ![位置权限](app-ui/16-location-permission.png) |

### 4.2 主导航与站点发现

| 步骤 | 页面 | 页面展示 | 用户动作 | 服务端/系统逻辑 | 下一步与异常 | UI截图 |
|---|---|---|---|---|---|---|
| DISC-01 | `MainTabs/Home` | 站点列表/地图、搜索、刷新、在线/可用摘要 | 搜索、切换列表/地图、刷新、点站点 | 查询公开站点和公开充电资源；退役/不可用资源不得被当作可充电资源 | → `StationDetail`；加载/空/网络错误提供刷新或解释 | ![首页](app-ui/02-home.png) |
| DISC-02 | `MainTabs/Saved` | 收藏站点或空状态 | 收藏/取消收藏/打开站点 | 收藏状态归属于当前用户；不能跨用户泄露 | → `StationDetail`；登录失效回登录 | ![收藏空状态](app-ui/17-saved.png) |
| DISC-03 | `StationDetail` | 站点名、地址、地图位置、开放状态、充电桩/connector、功率、枪型、价格、可用状态 | 收藏、导航、查看 connector、开始充电 | 服务端返回站点和设备公开投影；后端裁决状态和价格 | 有可用 connector → `Scan`；无可用 → 禁用并说明原因；刷新可重查 | ![站点详情](app-ui/03-station-detail.png) |
| DISC-04 | `MainTabs/Scan` | 相机扫码；Web 端手动输入 QR token | 扫码/粘贴 token/提交 | 解析 `qr:` 或原始 token；不把任意文本直接当成设备事实 | 合法 → `ChargingProcess`；非法/相机拒绝 → 具体错误、重试或手动输入 | ![扫码](app-ui/03-scan.png) |

### 4.3 充电启动前

| 步骤 | 页面状态 | 页面展示 | 用户动作 | 服务端/系统逻辑 | 下一步与异常 | UI截图 |
|---|---|---|---|---|---|---|
| CHG-01 | `ChargingProcess: checking` | 识别中、桩/connector 基本信息 | 等待或返回 | 查询设备在线、占用、connector、价格和当前用户资格 | → offline/charging_other/available；超时提供重试 | ![充电状态阻断](app-ui/31-charging-checking.png)<br>当前本地夹具在识别后立即返回离线阻断，未保留可见的 checking 中间帧。 |
| CHG-02 | `ChargingProcess: offline` | 桩 ID、最后在线时间、离线说明 | 重试/返回扫码 | 不允许启动，不创建收费充电事实 | 重试回 checking；返回 → `Scan` | ![充电桩离线](app-ui/04-charging-process.png) |
| CHG-03 | `ChargingProcess: charging_other` | 正在使用、桩/connector 状态 | 重试/返回 | 不允许抢占他人会话 | 重试回 checking；返回 → `Scan` | ![充电桩阻断态](app-ui/32-charging-offline.png)<br>当前测试夹具没有可复现的他人占用会话；此图是同一页面的真实阻断态，不能视作 `charging_other` 已验证。 |
| CHG-04 | `ChargingProcess: available` | 桩、connector、站点、地址、功率、枪型、价格模式、COP/kWh、支付规则 | 选择钱包、新卡或保存卡 | `paid` 才进入收费结算选择；`free` 显示免费说明；`unavailable` 禁止启动 | 未登录/欠费/风险预算阻断时进入对应恢复入口 | ![可用充电入口](app-ui/03-station-detail.png) |
| CHG-05 | `ChargingProcess: available + wallet` | 钱包余额、预期结算规则、开始按钮 | 点击开始充电 | 服务端执行 `chargingPreflight`，确认用户资格、余额/欠费、风险和设备状态；客户端不能自行裁决 | 允许 → 启动；阻断 → 错误/欠费/支持；重复点击必须幂等 | ![钱包支付入口](app-ui/05-wallet.png)<br>可用桩入口见 CHG-04。 |
| CHG-06 | `ChargingProcess: available + direct card` | 新卡/保存卡选择、结束后按准确金额扣款说明 | 点击进入支付 | 服务端创建 `charging_direct` Checkout Session；客户端打开托管页，不直接接触 Provider 密钥 | → `PaymentResult`/Provider 托管页；创建失败可重试且不重复建单 | ![银行卡托管入口](app-ui/30-mercado-pago-payment.png)<br>当前本地夹具离线，页面截图展示的是已进入的真实托管支付入口。 |

### 4.4 直接银行卡充电

1. 用户在 `ChargingProcess` 选择新卡或已保存卡。
2. 后端根据充电桩、站点、租户和支付策略创建 `Checkout Session`，客户端不得提交或选择收款主体、Provider、最终金额或 `tenant_id`。
3. 用户在 Mercado Pago 托管页完成卡信息、证件要求和必要的安全验证。
4. 用户返回 `payment-return` 或 App 恢复前台后，`PaymentResult` 查询同一个 Checkout Session。
5. 若状态为 `ready`，页面展示“卡已验证/可以开始充电”，但不能把支付 ready 当成设备已启动。
6. 用户点击“继续充电”，回到创建该 Checkout 时绑定的原始 `qrToken` 对应 `ChargingProcess`。
7. 用户再次明确点击“开始充电”，服务端执行资格检查和 OCPP 启动。
8. 充电停止后，系统按最终准确 Invoice 金额完成结算；失败或处理中进入恢复/欠费路径。

直接卡路径的关键产品不变量：

- 支付验证成功不自动启动设备；
- 返回后必须保留原始充电桩上下文，不能把用户丢回“充值”或普通扫码首页；
- 每个 Checkout Session 和 Card Token 只能安全使用一次；
- 页面停留超过 Session `expires_at` 后必须结束当前支付尝试并引导重新开始，不能无限轮询；
- Provider `processing` 不能被展示成成功，后台查询必须有上限，用户可以稍后回到同一上下文恢复；
- 当前产品是 EsLatin 平台统一收款，Vendor 不是 App 客户端可选择的收款方。

### 4.5 充电进行中、停止与完成

| 步骤 | 页面状态 | 页面展示 | 用户动作 | 服务端/设备逻辑 | 下一步与异常 |
|---|---|---|---|---|---|
| CHG-07 | `ChargingProcess: charging_self` | 充电中、已用 kWh、功率、SoC/电压/电流（有数据时）、桩/connector、停止按钮 | 刷新、停止、离开后返回 | 后端持续读取会话/计量；页面只显示服务端投影；轮询在页面/App 活跃时执行并有退避 | 断网可恢复；状态未知显示处理中，不伪造完成 |
| CHG-08 | `ChargingProcess: stopping` | 停止请求、等待设备确认 | 等待，不重复点击 | 发送幂等停止指令并等待 StopTransaction/会话关闭 | 成功 → `ChargingComplete`；超时 → 明确异常和支持/重试 |
| CHG-09 | `ChargingComplete` | 站点/设备、时间、kWh、价格快照、最终 COP、支付状态 | 查看历史、查看欠费、刷新结算、回首页/再次扫码 | 读取最终 Invoice、Payment/钱包/退款/Provider 收敛状态 | paid → 历史/首页；processing/unpaid → 继续确认或 `UnpaidBills`；退款/争议 → 状态和支持 |

### 4.6 支付与钱包

| 步骤 | 页面 | 页面展示 | 用户动作 | 服务端/支付逻辑 | 下一步与异常 | UI截图 |
|---|---|---|---|---|---|---|
| PAY-01 | `PaymentHub` | 钱包余额、充值预设金额、支付方式入口、交易入口 | 选充值、管理支付方式、看交易 | 充值使用 `wallet_top_up` Checkout；支付方式是非敏感摘要 | → 托管页/`PaymentMethods`/`MyWallet`；支付轨关闭时说明不可用 | ![支付中心](app-ui/07-payment-hub.png) |
| PAY-02 | `MyWallet` | 余额、充值/扣款流水、充值按钮 | 充值、查看交易 | 钱包账本由服务端维护，Provider 通知幂等入账 | 成功回余额并刷新；processing 不能直接增加余额 | ![我的钱包](app-ui/05-wallet.png) |
| PAY-03 | `PaymentMethods` | 卡品牌、类型、末四位、默认标记、删除/设默认 | 添加、设默认、删除 | 只展示 Provider 返回的非敏感投影；删除要确认并服务端裁决 | → `AddPayment`；失败可重试；不存在时显示空状态 | ![支付方式](app-ui/08-payment-methods.png) |
| PAY-04 | `AddPayment` | 添加银行卡说明、托管支付入口、保存卡提示 | 打开并完成安全页 | 创建 `save_card` Checkout；CVV/证件/PAN 不进入 EsLatin | 成功 → `PaymentMethods`；过期/拒绝 → 可重新添加 | ![添加支付方式](app-ui/09-add-payment.png) |
| PAY-05 | `MercadoPagoPayment` | 当前兼容入口的充值托管流程 | 完成钱包充值 | 当前仅服务 `wallet_top_up`，不作为新增充电业务 API | 成功 → `PaymentResult`/钱包；失败有重试 | ![充值托管入口](app-ui/30-mercado-pago-payment.png) |
| PAY-06 | `PaymentResult` | 支付目的、金额摘要、当前状态、下一步按钮 | 等待、查询状态、打开必要验证、继续充电、返回 | 查询同一个 Session；状态按服务端/Provider 事实收敛 | 见第 6 节支付状态机 | ![支付结果处理中](app-ui/21-payment-result.png) |

### 4.7 欠费与补缴

| 步骤 | 页面 | 页面展示 | 用户动作 | 服务端/账务逻辑 | 下一步与异常 |
|---|---|---|---|---|---|
| REC-01 | `UnpaidBills` | 账单列表、来源充电、未结金额、阻断原因、当前状态 | 选择账单、刷新、进入支持 | 只读取当前用户的服务端账单投影，不允许改金额 | → `UnpaidBillDetail`；加载失败可重试 |
| REC-02 | `UnpaidBillDetail` | 原充电站点/设备、时间、kWh、价格快照、未结额、阻断说明、支付方式 | 钱包/新卡/保存卡补缴、联系客服 | 创建 `RecoveryAttempt`，金额固定为服务端未结金额；最终结清前保持阻断 | 成功但处理中 → 继续确认；失败 → 重试/支持；结清 → 刷新列表和资格 |
| REC-03 | 补缴结果 | 处理中、成功、拒绝、过期、未知 | 查询/返回 | Provider/Webhook/主动反查收敛；客户端不得单独解除 D1 | 足额结清且无其他阻断账单 → 可重新进入充电；否则继续阻断 |

### 4.8 账户、历史与支持

| 页面 | 展示与动作 | 规则 | UI截图 |
|---|---|---|---|
| `Account` | 个人资料、充电历史、支付中心（支付轨启用时）、语言、支持、帮助、隐私、关于、退出 | 退出后清理本地会话和待恢复支付引用；不能用旧页面继续充电 | ![账户](app-ui/06-account.png) |
| `PersonalInfo` | 账户资料和可编辑字段 | 只修改允许的用户资料，不改变账务/租户事实 | ![个人资料](app-ui/18-personal-info.png) |
| `Language` | 西班牙语、英语、中文 | 切换后更新 UI 文案；服务端时间仍按 UTC 存储 | ![语言](app-ui/19-language.png) |
| `ChargingHistory` | 充电记录列表、状态筛选/加载/空状态 | 记录状态必须与 Invoice/Payment/Refund 事实一致 | ![充电历史](app-ui/20-charging-history.png) |
| `ChargingHistoryDetail` | 站点、设备、connector、开始/结束、kWh、价格、COP、支付/退款/争议状态、支持入口 | “已启动”不能等于“已付款”；展示未知/处理中，不伪造成功 | ![充电历史详情](app-ui/23-charging-history-detail.png) |
| `SupportCases` | 当前用户工单列表和状态 | 工单不能改写财务事实；展示关联号和状态 | ![支持案件空状态](app-ui/24-support-cases.png) |
| `SupportCaseDetail` | 问题上下文、消息/状态、退款或支持请求 | 不要求用户提交完整卡号、CVV、证件号或 Provider 密钥 | ![支持详情入口空状态](app-ui/25-support-case-detail.png)<br>当前测试账户没有案件，详情页无可进入实例。 |
| `HelpCenter` | 常见问题和操作说明 | 对支付、充电、欠费和设备异常提供下一步 | ![帮助中心](app-ui/26-help-center.png) |
| `PrivacyPolicy` | 隐私与数据使用说明 | 不展示敏感配置或内部密钥 | ![隐私政策](app-ui/27-privacy-policy.png) |
| `About` | 品牌、版本和法律信息 | 不展示敏感配置或内部密钥 | ![关于](app-ui/28-about.png) |

## 5. 页面状态与通用交互规则

### 5.1 所有页面通用状态

每个读取或提交动作都必须能区分以下状态：

1. `loading`：首次加载或提交中，禁止产生重复动作；
2. `ready`：数据可用，展示主要 CTA；
3. `empty`：没有数据，解释原因和下一步；
4. `offline/network_error`：网络不可用，保留用户上下文并提供重试；
5. `processing`：服务端/Provider/OCPP 尚未最终收敛，不能当作失败或成功；
6. `failed/declined`：可行动失败，说明是否可重试；
7. `expired`：当前会话/链接不能继续，清理过期引用并重新开始；
8. `blocked`：前置资格、欠费、桩状态或支付轨阻断，必须显示原因和可行恢复路径。

### 5.2 返回、刷新与重新进入

- 返回不会取消已经由服务端创建的 Checkout、充电会话或补缴尝试；页面必须先查询服务端事实。
- 从 Provider 返回时优先恢复 `checkout_session_id`、支付目的和原始充电 QR 上下文；不能把 `charging_direct` 随意变成钱包充值。
- 页面刷新或 App 冷启动时，若存在未完成 Checkout，Root Navigator 恢复到 `PaymentResult`，再按服务端状态导航。
- 过期 Checkout 清理 pending 引用；用户必须重新发起一个新的流程。
- 充电会话进行中离开页面后重新进入，先查询 active session；不得从本地缓存推断仍在充电。
- 网络错误只允许安全重试；重复点击由 UI 锁定和服务端幂等共同保证。

### 5.3 资金和设备边界

- 支付成功不等于 OCPP 启动成功；设备启动成功也不等于最终 Invoice 已支付。
- 充电用量来自设备/后端事实，价格来自冻结的价格快照，金额由服务端计算。
- App 不保存 PAN、CVV、证件号、Access Token、Webhook Secret 或原始 Provider Card Token。
- App 不提交或选择 `provider`、收款主体、`tenant_id`、`collector_id`、`application_fee` 或最终账单金额作为授权事实。
- 页面显示的“在线/可用/已支付/已结清/已退款”必须能回溯到对应服务端状态，不得依赖乐观 UI。

## 6. PaymentResult 状态机

```mermaid
stateDiagram-v2
    [*] --> created
    created --> ready: 服务端确认支付准备完成
    created --> processing: Provider 处理中
    created --> action_required: 需要验证
    created --> declined: 拒绝
    created --> expired: Checkout 过期
    created --> error: 创建/查询错误
    ready --> ChargingProcess: charging_direct + 用户继续充电
    ready --> [*]: 其他目的按目的路由
    action_required --> processing: 用户完成验证
    processing --> approved: Provider/主动反查确认
    processing --> declined: Provider 拒绝
    processing --> expired: Session 过期
    processing --> error: 最终错误
    approved --> [*]: wallet_top_up/save_card/unpaid_charge 按目的完成
    declined --> [*]: 失败并可安全重试
    expired --> [*]: 清理上下文并重新开始
    error --> [*]: 展示恢复/支持
```

| 状态 | 页面用户含义 | 允许动作 | 禁止动作 |
|---|---|---|---|
| `created` | 已创建，正在准备 | 等待/查询 | 重复创建同一业务支付 |
| `ready` | 支付凭证已准备，尚未代表设备启动 | `charging_direct` 回原充电页并明确开始 | 自动启动设备 |
| `processing` | Provider 尚未给出最终事实 | 有上限的查询、返回后稍后恢复 | 直接判定成功、重复支付 |
| `action_required` | 需要用户完成验证 | 打开验证页、完成后返回 | 跳过 Provider 验证 |
| `approved` | Provider/后端确认支付成功 | 按支付目的收敛业务 | 直接改写 Invoice 或重复入账 |
| `declined` | 支付被拒绝 | 重新开始/更换支付方式/支持 | 启动依赖该支付的充电 |
| `expired` | Checkout 已失效 | 重新发起 | 继续提交旧 Card Token/Session |
| `error` | 创建或查询失败 | 重试/返回/支持 | 伪造成功或清除账务阻断 |

当前 App 对非终态查询必须有明确上限；回到 App 前台、页面聚焦和用户主动点击可触发一次查询，但不得建立无限后台轮询。Hosted Checkout Session 的有效期以服务端 `expires_at` 为准，当前产品定义为创建后 10 分钟，剩余 2 分钟进入警告态。

## 7. 充电会话状态机

```mermaid
stateDiagram-v2
    [*] --> checking
    checking --> offline
    checking --> charging_other
    checking --> available
    available --> preflight
    preflight --> blocked
    preflight --> starting
    available --> checkout_required: direct card
    checkout_required --> payment_ready
    payment_ready --> starting: 用户明确继续
    starting --> charging_self
    charging_self --> stopping: 用户/设备停止
    stopping --> settling
    settling --> complete_paid
    settling --> complete_processing
    settling --> complete_unpaid
    complete_unpaid --> recovery
    recovery --> complete_paid
```

产品层面必须保持以下顺序：

`识别设备 → 核验状态/资格 → 选择结算方式 → 必要时完成 Checkout → 用户明确启动 → OCPP 启动 → 计量 → 停止 → 最终 Invoice → 支付/欠费恢复`。

任一阶段失败都不能跳过前置事实，也不能用下一页面的乐观展示掩盖当前状态。

## 8. 关键异常与用户恢复矩阵

| 异常 | 页面表现 | 用户可做什么 | 服务端必须保证 |
|---|---|---|---|
| 登录网络错误 | 西语可行动错误，不显示空白页 | 重试、检查连接 | 不创建半登录状态 |
| 站点加载失败 | 加载错误/刷新 | 刷新或返回 | 不把缓存旧状态当实时在线 |
| QR 无效 | QR 错误 | 重新扫码/手动输入 | 不调用任意设备启动 |
| 桩离线 | 离线原因/最后在线 | 重试/返回 | 不创建充电会话 |
| 桩被他人使用 | 使用中 | 重试/返回 | 不抢占他人会话 |
| 欠费阻断 | 未结账单和补缴入口 | 查看/补缴/支持 | 足额结清前保持 D1 |
| Checkout 创建失败 | 支付不可用/重试 | 重试或改用钱包 | 幂等，不重复建单 |
| 3DS/Provider 验证 | 需要验证 | 打开并返回 | 不把未完成验证判定为成功 |
| Provider processing | 确认中 | 等待/查询/稍后恢复 | 有上限查询，Webhook/反查收敛 |
| Checkout 过期 | 已过期 | 重新开始 | 旧 Session/Card Token 不可继续使用 |
| 充电启动失败 | 未开始/启动失败 | 重试或支持 | 不把支付 ready 当成设备已启动 |
| 充电中断 | 处理中/异常 | 等待恢复、停止/支持 | OCPP、Session、Invoice 状态一致 |
| 停止超时 | 停止确认中 | 等待/支持 | 幂等停止并按风险规则升级 |
| 最终支付失败 | 未结账单 | 补缴/支持 | 不伪造已支付，按 D1 规则处理 |
| 重复回跳/Webhook | 页面不重复变化 | 正常继续 | 不重复入账、扣款、解锁或退款 |

## 9. 产品验收清单

### 9.1 账号与导航

- [ ] 新用户可以注册、验证、登录并进入主导航。
- [ ] 已登录用户刷新/重开后不会丢失或错误恢复支付/充电上下文。
- [ ] 退出后受保护页面不能继续执行充电或支付。
- [ ] 主导航五个入口均有 loading、空、错误和恢复状态。

### 9.2 发现与充电

- [ ] 站点详情显示地址、在线状态、connector、功率、枪型、价格和可用性。
- [ ] 退役/不可用设备不会作为可启动设备展示。
- [ ] 相机和 Web 手动 QR 都能正确进入对应 `ChargingProcess`。
- [ ] 离线、他人使用、价格 `unavailable` 和资格阻断都有可行动提示。
- [ ] 钱包充电和直接刷卡充电是两条可区分、可验证的产品路径。
- [ ] 充电结束后展示最终 Invoice/支付状态，不把启动成功当付款成功。

### 9.3 支付与恢复

- [ ] 直接刷卡回跳后回到原始充电桩，不被送到普通充值页面。
- [ ] `ready` 只允许用户继续启动，不自动启动设备。
- [ ] 充值成功只增加一次钱包余额。
- [ ] 保存卡成功后只显示品牌、类型、末四位和默认状态。
- [ ] 过期、拒绝、处理中、验证失败和网络恢复均有明确分支。
- [ ] 欠费账单可以查看来源和金额；补缴足额后才可能解除阻断。
- [ ] 重复点击、刷新和重复 Webhook 不产生重复资金事实。

### 9.4 历史与支持

- [ ] 历史列表和详情能够区分充电、账单、支付、退款、争议和处理中。
- [ ] 详情可进入支持，支持不要求敏感支付数据。
- [ ] 用户看不到 PAN、CVV、证件号、Token、Webhook Secret 或内部收款配置。
- [ ] 所有关键页面支持西语首要文案，并且状态不只靠颜色表达。

## 10. 当前实现与后续工作边界

### 当前已定义/已有页面承载

- 身份、首页/站点发现、收藏、扫码、充电启动/监控/停止、钱包、支付方式、托管支付结果、充电历史、账户和基础支持入口。
- 钱包、直接新卡、保存卡和欠费补缴使用同一 Checkout Session 产品边界，通过 `purpose` 分流。
- 设备状态、价格、充电用量、最终金额和支付结果由服务端事实驱动。

### 仍需独立验证或补齐的内容

- Mercado Pago Sandbox/3DS 的真实浏览器闭环和所有 Provider 最终状态证据。
- 充电结束后的准确金额扣款、Webhook、结算、对账和资金三方匹配的跨模块 E2E。
- 欠费列表、补缴恢复和跨模块解锁的完整用户体验验收。
- 生产 Provider、DNS/TLS、备份恢复、告警、回滚和人工 release review。
- 地图能力在不同运行平台的实际可用性；Web 端若没有地图能力或密钥，应显示明确的降级状态，不阻断手动地址/列表路径。
- RefundCase 运营审批和完整支持运营流程仍以现有产品范围和门禁状态为准，不能因本页面文档自动视为完成。

上述项目是验收/工程门禁，不是本次文档新增的产品承诺；完成前不得把文档中的“预期结果”当作“已经通过”。

## 11. 关联文档与维护规则

- 全局产品架构：`docs/product/PRODUCT_ARCHITECTURE.md`
- 支付产品：`docs/features/PAY-MP-001/product/PRD.md`、`docs/features/PAY-MP-002/product/PRD.md`
- 首页/搜索：`docs/features/APP-HOME-SEARCH-001/PRD.md`
- 账户：`docs/features/APP-ACCOUNT-001/PRD.md`、`docs/features/APP-ACCOUNT-002/PRD.md`、`docs/features/APP-ACCOUNT-003/PRD.md`
- 充电恢复：`docs/features/APP-RECOVERY-001/PRD.md`
- 价格模式：`docs/features/PRC-MODE-001/PRD.md`
- 交互 QA 计划：`docs/features/PAY-MP-002/qa/PRODUCT_INTERACTION_TEST_PLAN.md`
- 当前技术架构：`docs/architecture/TECH_ARCHITECTURE.md`

维护要求：

1. 新增页面、改变用户旅程、改变支付目的或改变用户可见状态，先更新本文件和对应产品决策/feature 文档。
2. 新增重大支付、收费、退款、欠费、身份或消费者承诺时，必须经过 Human Product Decision Gate；推荐不等于批准。
3. 页面文案不能独立发明后端状态；新状态先进入产品/契约和技术架构审查。
4. QA 报告只记录实际证据，不把本文件中的预期结果改写成测试通过。
5. 本文档修改只描述产品行为；前端实现、API、数据库、配置和部署变更必须分别经过对应 owner 和门禁。
