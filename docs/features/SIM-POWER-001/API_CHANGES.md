---
id: SIM-POWER-001
status: ready-for-dev
---

# 接口与配置变化

## 服务端 API

无变化。

## 数据库

无变化，不新增迁移。

## charger-sim CLI

`run-one` 新增：

```text
--shared-power-limit-kw FLOAT
```

省略时保持旧行为；提供时必须大于 0。

## run-many 配置

单个 charger 对象新增可选字段：

```yaml
shared_power_limit_kw: 60
```

`power_kw` 继续表示每个枪口的请求/最大功率。共享上限只限制同一 charger
对象中的活跃 `connector_ids`。
