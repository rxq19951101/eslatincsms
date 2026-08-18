# EsLatin 当前技术架构

> 状态：current baseline  
> 基线日期：2026-08-17
> 维护角色：architecture-agent

## 1. 系统概览

EsLatin 当前是模块化单体仓库：FastAPI CSMS 同时承载 REST、OCPP WebSocket、后台任务和支付回调；Next.js Admin 与 Expo React Native App 通过 HTTPS REST 使用后端；PostgreSQL 保存权威业务事实，Redis 保存实时/短期状态、幂等和协调数据。生产通过 Docker Compose 部署，由外部 DNS/TLS 入口暴露 Admin、API 与 OCPP WSS。

## 2. 架构原则

- PostgreSQL 是持久业务事实源；Redis 不是账务事实源。
- 所有租户业务查询从已认证身份/可信设备绑定推导 tenant，不信任客户端 tenant_id。
- REST schema/错误码是前后端契约；UI 不补造后端事实。
- OCPP/支付/Webhook/远程指令必须幂等并具有明确状态迁移。
- 金额使用 Decimal/十进制字符串；时间以 UTC 持久化。
- 高频遥测分为实时快照与持久采样，限制数据库写放大。
- 外部 Provider 通过 adapter/service 边界接入，Provider payload 不泄漏为核心域模型。
- 敏感数据最小化：卡与证件数据不进入 App、常规 API、数据库或日志。

## 3. 运行时组件

### CSMS Backend

- 技术：Python、FastAPI、SQLAlchemy、PostgreSQL、Redis。
- 入口：`csms/app/main.py`。
- HTTP API：`csms/app/api/v1/`，区分 App、Admin 和运营资源路由。
- 业务服务：`csms/app/services/`。
- 领域状态：`csms/app/domain/`。
- 数据模型：`csms/app/database/models.py`。
- OCPP：`csms/app/ocpp/`、transport manager、message handler 和 control API。
- 后台能力：离线检测、监控循环、可选 Redis Streams 分布式路由。

### Admin Web

- 技术：Next.js 16 App Router、React 19、TypeScript、SWR、Zustand。
- 目录：`admin/app`、`admin/components`、`admin/features`、`admin/lib`。
- 职责：运营管理、地图、资产、用户/权限、价格、交易、支付、告警、统计。
- Admin 不直接访问数据库或 Provider。

### Consumer App

- 技术：Expo 54、React Native 0.81、React Navigation、Redux Toolkit、Axios、AsyncStorage。
- 目录：`app/src/screens`、`components`、`features`、`api`、`store`、`navigation`、`i18n`。
- 职责：公开发现、账户、扫码充电、钱包、支付、订单和恢复状态。
- 只持久化非敏感恢复引用；托管支付页由后端提供。

### Charger Simulator

- 目录：`charger-sim/`。
- 职责：OCPP 设备模拟、手动场景、可重复 E2E；不得成为生产业务依赖。

## 4. 后端领域边界

### Identity/Tenant/Permission

认证中间件验证 token audience；租户中间件加载数据库确认身份和成员关系。AdminUser、AppUser、Tenant、Membership、Role 和 AuditLog 形成授权边界。系统级超级管理员与租户级角色分离。

### Asset/Site

Site、ChargePoint、EVSE、Device 及配置归属租户。公开资源由 App API 输出安全投影；运营写操作由 Admin/运营 API 校验租户和权限。退役/删除策略必须保留历史引用。

### OCPP/Realtime

WebSocket `/ocpp` 由 transport manager 管理连接，消息交给 OCPP message handler。ChargePoint OCPP identity 是外部设备标识，数据库 UUID 是内部关联。生产默认预注册和凭据校验。Redis 维护在线/路由/幂等短期状态；PostgreSQL 保存会话、采样和审计事实。

### Charging/Pricing/Billing

ChargingSession 记录设备会话事实；Tariff/PricingSnapshot 冻结计价事实；Invoice 记录应收；Order/Payment 记录交易状态。定价域不处理支付，支付域不修改用量。充电启动使用服务端校验过的 QR、桩、connector、租户和 Payment Intent。

PAY-MP-001 当前仍是结束后按实际 Invoice 结算；`Order.pre_authorization` 只保存非敏感 Charging Payment Intent，不代表 Provider authorization。`Invoice` 对 Session 保持唯一关系，补缴/恢复不得改写原账单、用量或 PricingSnapshot。D1 必须由 PostgreSQL 财务事实服务端判定，不能由 App、Redis 或 `AppUser.has_unpaid_charges` 作为最终解锁依据。

### Payment/Wallet

payment checkout service 是唯一 App 支付入口，负责有签名的托管 Session、Redis 单次 token、Confirm、结果查询与安全状态页。当前产品只启用 Mercado Pago；App 不携带 Provider、收款主体或凭证。Provider adapter/registry、credential resolver 和 merchant context 位于服务端内部，Provider-specific Webhook 适配器只把外部事实映射到统一 PaymentOrder/Checkout 状态机。钱包交易与直接卡支付是独立结算分支，但支付创建都通过 Checkout Session 的 `purpose` 表达。

当前公共边界为：`/api/v1/app/payments/checkout-sessions`、其 hosted checkout/confirm/query 子路径、`/api/v1/app/payment-methods`，以及独立的 `/api/v1/app/payments/webhooks/mercadopago` 和测试 `/webhooks/sim`。历史 Wompi、旧 Mercado Pago create/status 和旧 webhook 路由不再注册为当前 API。

未来 Provider 只能新增 Adapter、Credential Resolver、Webhook Adapter 和对应测试，不得新增 `/create-<provider>`、`/pay-<provider>` 或第二套 App checkout 契约。

当前 Provider adapter 是 Payments API 自动支付、查询和退款边界，没有 authorize/capture/void/partial-capture/chargeback 领域协议；`PaymentOrder` 不是授权单，退款摘要也不是完整退款/争议事实。PAY-MP-002 的 BE-201～BE-211 后端实现和独立 QA 已覆盖 typed recovery/allocation、refund/chargeback、三方 reconciliation、runtime rail control 与结构化 support case 的批准测试范围；这些能力仍需完整前端运营旅程、live Provider、生产容量和人工发布门禁，不能据此宣称生产已可用。

### Operations

Alerts、SystemConfig、SupportMessage、statistics、monitoring 和 audit 提供运营能力。关键配置有全局与租户覆盖关系，不允许业务模块直接绕过配置服务建立隐藏默认值。

支付 Admin API 已具备批准范围内的细粒度权限、资源 scope、退款/对账例外双控和 rail close/reopen authority；BE-209/BE-210 独立 QA 已覆盖对应 backend gate。Admin 完整运营 UI、真实运行时和跨模块生产验收仍未闭合。`PAYMENT_RAILS_ENABLED` 仍是部署环境总门禁，不是可由普通配置或前端写入的运行时紧急关闭。

## 5. 数据架构

- PostgreSQL 15 保存 Tenant、用户/成员/角色、站点/设备、会话/计量、价格快照、Invoice/Order/Payment、钱包、Webhook、告警、配置和审计。
- 主要租户模型包含 tenant_id；跨租户后台操作必须使用受控 super session，并在服务层显式裁决。
- Schema 由 Alembic 管理；空库和既有库都必须通过可重复版本链建立，不依赖运行时 `create_all`。
- Redis 7 用于实时在线状态、短期去重、Checkout Session/token、限流/协调和可选分布式 OCPP 路由；Redis 丢失不能伪造已支付或已结算事实。
- Outbox/Event 模型用于需要可靠异步交接的领域事实，禁止跨域直接读取并修改彼此表作为隐式消息总线。PAY-MP-002-v1 的单表 additive scope、tenant/platform `scope_type/scope_ref`、DB CHECK 和 scope 唯一键已有 BE-201 独立 QA 证据；测试 Compose 仍没有完整 Outbox consumer drain 证据。
- PAY-MP-002 的 recovery/allocation、refund/approval、chargeback/dispute、reconciliation、rail-control 和 support typed authority、唯一键与重放边界已有 BE-201～BE-211 实现/QA 证据。生产级 worker lease/retry/DLQ/replay、PostgreSQL/Redis 实际容量和异步收敛仍需独立运行时验收；可重建 read model 不能成为 D1、结算或风险预算权威。D-204 risk facts 不在当前批准实现范围。

## 6. API 与契约边界

- `/api/v1/app/*`：App audience；只返回当前用户或公开资源。
- `/api/v1/admin/*`：Admin audience；按角色和租户授权。
- `/api/v1/*` 运营资源：必须由依赖和中间件明确保护，不得因历史路由而绕过租户。
- `/ocpp/*`：设备 WebSocket 身份边界，不使用 App/Admin JWT。
- `/health`、metrics：最小公开运维面；生产文档接口默认关闭。
- HTTP/验证错误使用统一安全错误契约；Provider 原始错误不直接传给客户端。

## 7. 支付数据流

1. App 创建不含卡数据的 Checkout Session。
2. Backend 校验 purpose/mode/save_card 矩阵并返回同源签名 URL。
3. Browser 加载 MercadoPago.js Secure Fields；证件和卡 token 直接送 Provider SDK。
4. Backend Confirm 只接收短期 token/必要非敏感事实并消费 Session。
5. Provider 返回或 3DS 后，Backend 建立 Payment Intent/保存卡投影/充值结果。
6. App 只通过 GET 查询服务端状态，409/503/网络未知不创建重复 Session。
7. Webhook 经签名和主动反查进入 reconciliation，校验金额、币种、商户、租户和状态顺序。
8. 充电结束后 Invoice 为金额权威，支付域执行钱包扣款或直接卡扣款。

PAY-MP-002 的补缴、FinancialEligibility、D1 re-block、Charging paid-admission preflight、P001/P002 投影和历史安全边界已有对应后端/前端实现及独立测试证据；完整 App 欠费/恢复 UI、Admin 运营 UI、真实 Provider/Webhook、生产容量和人工发布门禁仍未完成。D-204 未批准前不建立风险预算运行时；任何未来 Provider authorization/capture 仍需独立产品与架构门禁。

生产支付轨由 `PAYMENT_RAILS_ENABLED` 总门禁控制；QA 和人工审查完成前必须关闭。

## 8. OCPP 数据流

桩以 OCPP identity/secret 连接 → transport 验证预注册设备 → Boot/Heartbeat/Status 更新实时状态 → RemoteStart/Stop 通过连接路由 → StartTransaction 创建/绑定 ChargingSession → MeterValues 更新实时快照并按策略采样 → StopTransaction 结束会话 → Billing 读取会话与 PricingSnapshot 生成 Invoice → Payment 完成结算。

当前数据流没有 PAY-MP-002 风险预算硬止损，D-204 继续禁止默认实现。若后续获得明确批准，支付/风险域只能通过服务端 preflight、版本化风险决策和既有 Outbox/OCPP control 交接 RemoteStart/RemoteStop；`StartTransaction` 不是支付成功，发送 RemoteStop 也不是设备已停止，必须等待 StopTransaction/最终 MeterValues。支付服务不得直接改写 Session/MeterValues 或持有 ChargePoint socket；Provider Webhook、rail close 和对账不得吞掉进行中 OCPP 事实。

## 9. 前端架构

- App 和 Admin 各自拥有 API adapter，不复制后端业务规则。
- App Redux 保存跨屏业务状态；功能 coordinator（如 payment checkout）集中恢复和 in-flight 去重。
- AsyncStorage 只保存非敏感 token/reference；Deep Link 参数受长度、状态与 host allowlist 限制。
- 多语言 business status 使用集中映射，不把未知值猜成成功或信用卡。
- Admin Server/Client 组件边界由 Next.js 约束；共享组件不得持有租户授权逻辑。

## 10. 部署架构

- 本地默认：Docker Compose，PostgreSQL、Redis、CSMS、Admin，可选 simulator/E2E profile；App 通常由 Expo 独立运行。
- 生产：`docker-compose.prod.yml`，PostgreSQL/Redis 不直接暴露公网，CSMS/Admin 经反向代理和 TLS 域名访问。
- 预期域名：`admin.eslatin.com.co`、`api.eslatin.com.co`；OCPP 地址 `wss://api.eslatin.com.co/ocpp/<identity>`。
- 生产 secrets 仅通过环境/secret provider 注入；不进入 Git。日志限制大小并进行敏感信息清洗。
- 当前为单 VPS 可部署架构；可选 distributed OCPP 路由不是默认生产假设。

## 11. 允许依赖

- API → service/domain → database/provider adapter。
- Charging → pricing snapshot、billing contract、payment intent contract。
- Payment reconciliation → provider adapter、Order/Payment/Invoice，但不能修改 OCPP 用量。
- Frontend → frozen HTTP contract，仅通过 Backend 访问持久事实和 Provider。

## 12. 禁止依赖

- Frontend/Admin → PostgreSQL、Redis 或 Mercado Pago secret API。
- Provider adapter → UI、OCPP transport 或租户无关全局可变状态。
- OCPP message handler → 前端状态或支付 Provider 直接调用。
- 租户服务 → 客户端 tenant_id 作为授权结论。
- 一个领域直接改写另一个领域的权威金额/状态表以绕过其 service。
- 使用 Redis、日志或 UI 状态替代账务、支付或充电数据库事实。

## 13. 扩展与安全假设

- 当前单体可通过数据库池、Redis 和多实例路由扩展，但多实例 OCPP 必须显式启用并验证连接归属。
- 高频事件必须限频、聚合或采样；不得恢复无界 HeartbeatHistory/MeterValues 写入。
- 外部请求有 timeout、重试和幂等边界；不在请求链中进行无界阻塞。
- 密钥轮换、Webhook 重放保护、支付对账、租户隔离和审计是生产安全边界。

## 14. 已知架构债务/门禁

- 历史支付实现仍可在源码中作为未注册 legacy router 留存，不能被新 App 调用；后续清理属于独立 C1/C2 变更，不影响当前 canonical contract。
- 数据模型集中于单一大型 `models.py`；按领域拆分需 ADR 和迁移安全计划。
- 真实 Sandbox/3DS、live Provider/Webhook 与完整跨模块 E2E 未完成，生产支付轨不得打开。
- 欠费完整 App UI、完整 Admin 运营 UI、C2 分账和异常对账工作台尚未形成生产可验收能力。
- PAY-MP-002 C3 第二次且最后一次限定复审（CHG-20260812-002）为 `approved`：BE-201～BE-211、FE-201 已有独立 QA 终态，`PAY-MP-002-v1` 已冻结。当前生产 NO-GO，Sandbox Provider 子门禁 pending；D-204 单独阻塞 BE-205、风险参数/UI/runtime 和真实资金发布。
