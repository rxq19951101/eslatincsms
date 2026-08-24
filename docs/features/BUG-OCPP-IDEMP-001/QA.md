---
id: BUG-OCPP-IDEMP-001
status: accepted
tested_at: 2026-08-03T04:54:09Z
---

# QA 结果

## 自动化测试

- `docker compose exec -T csms pytest -q tests/test_api_ocpp_control.py -k 'remote_start' --maxfail=1`
  - 结果：`8 passed, 26 deselected`
- `docker compose exec -T csms pytest -q tests/test_api_ocpp_control.py --maxfail=1`
  - 结果：`34 passed`

## Compose 真实链路

- 重建并重启 `csms` 后运行 `p0-admin-happy-path`。
- 远程启动首次返回 200，模拟桩只收到一次 `RemoteStartTransaction`。
- 模拟桩上报 `StartTransaction`、`Charging` 和 `MeterValues` 后，相同幂等键重放仍返回 200。
- 场景确认重放没有再次下发设备命令，随后远程停止成功，会话进入 `completed`。
- 结果：`PASS scenario=p0-admin-happy-path run_id=e669005b-bfe0-46d0-81d5-880026dfd1c3`。

## 结论

验收通过。未执行数据库迁移；未部署生产环境。
