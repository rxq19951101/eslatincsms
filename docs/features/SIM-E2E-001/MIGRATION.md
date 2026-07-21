# 迁移计划

1. 移除版本库中的支付测试账号文件，用 `.example` 占位并加入忽略规则。
2. 保留旧 CLI 的 `run-one/run-many/gen-qr` 兼容壳，内部转到新 actor。
3. 新增场景 schema 与 P0 场景包。
4. 修正 CSMS OCPP 与 App UUID 契约。
5. 使用空本地数据库建立固定 E2E 数据集。
6. 启动 Admin、App Web、CSMS 和场景 runner；原生端作为平台冒烟。
