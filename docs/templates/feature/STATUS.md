---
id: <REQ-ID>
status: draft
product: draft
contract: draft
backend_design: not-started
backend_implementation: not-started
backend_qa: not-started
frontend_design: not-started
frontend_implementation: not-started
frontend_qa: not-started
e2e_qa: not-started
human_review: not-started
product_decision_gate: not-required | options-prepared | awaiting-user-approval | user-approved
product_approval_record: not-required | missing | present
---

# 需求状态

## 当前阶段

- 当前负责人：
- 当前任务：
- 文件所有者：
- 阻塞项：

## 产品决策门禁

产品状态机固定为：

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

- 未解决的重大产品选择必须先设为 `awaiting-user-approval`。
- 只有用户明确点名具体方案/决策编号的回复，且已记录在 `docs/changes/<CHANGE_ID>/PRODUCT_APPROVAL.md`，才能设为 `user-approved`。
- 推荐、沉默、“继续/推进/ok/确认”、技术可行性和历史决定都不能转换状态。
- `PRODUCT_APPROVAL.md` 缺失时，architecture-agent 只能做非约束性 feasibility/modeling，并返回 `blocked: awaiting-explicit-user-product-decision`。

## 最近交接

- Agent：
- 结果：
- 测试证据：
- 下一门禁：
