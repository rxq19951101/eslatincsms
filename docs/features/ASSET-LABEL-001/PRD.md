---
id: ASSET-LABEL-001
status: ready-for-dev
---

# 运营资产与充电枪公共展示标识

App 用户和普通租户运营人员必须通过业务可理解、可与现场设备对应的名称识别站点、充电桩、充电枪和充电会话。OCPP、EVSE 和数据库内部标识不得作为默认产品名称。

## 展示层级

- 站点：站点名称。
- 充电桩：`display_name` 优先，`display_code` 作为稳定运营编号；没有名称时使用 `display_code`。
- 充电枪：可选现场编号 `physical_reference` 优先，否则由客户端按 `connector_number` 国际化为“充电枪 1 / Connector 1 / Conector 1”。
- 充电会话：使用业务会话编号；OCPP transaction ID 只属于技术诊断信息。

## 产品边界

- App 不返回、不展示 OCPP Identity、OCPP transaction ID、EVSE ID 或数据库 UUID 作为名称。
- Admin 默认运营界面不得回退显示 OCPP Identity、EVSE ID 或数据库 UUID。
- Admin 接入与诊断区域可显示并复制协议标识。
- 远程启停继续在服务端使用协议标识，不改变既有命令、幂等和审计逻辑。
- App 与 Admin 的充电枪编号和现场设备标签必须一致。

## 多语言

- 中文默认名：`充电枪 {number}`。
- 英文默认名：`Connector {number}`。
- 西班牙语默认名：`Conector {number}`。
- 服务端只返回稳定数据字段，不返回已翻译的默认名称。

