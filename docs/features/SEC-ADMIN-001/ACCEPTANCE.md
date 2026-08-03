---
id: SEC-ADMIN-001
status: ready-for-dev
---

# 验收标准

- [x] `npm audit --omit=dev` 不再报告生产依赖漏洞。
- [x] 完整 `npm audit` 不再报告 critical 或 high 漏洞。
- [x] Admin 定向测试全部通过。
- [x] Admin 生产构建成功。
- [x] 不修改业务 API 契约和数据库结构。
