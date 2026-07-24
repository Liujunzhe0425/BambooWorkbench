---
request_id: FCR-moisture-20260724-rule-management-snapshot
module_id: moisture
module_version: 1.1.0
owner: moisture 模块负责人
status: superseded_by_unified_contract
framework_areas:
  - ui
  - management
  - workflow
  - storage
breaking_change: false
required_before_module_merge: true
superseded_by: FCR-moisture-20260724-public-management-contract
---

# 框架适配请求：轻量规则管理与任务快照

> 本文件不再单独定义公开进程合同。
> 唯一有效的公开合同、操作名、字段、错误码、规则身份查询和任务快照要求见：
>
> `FCR-moisture-20260724-public-management-contract.md`

## 保留的业务目标

规则管理继续采用三栏：

```text
规则草稿 | 当前有效规则 | 历史版本
```

模块继续复用现有：

- `RuleDefinition`、规则包 Schema 和 Evaluator；
- 草稿、不可变发布版本、active/retired 指针；
- 创建、更新、校验、预览、发布、停用、恢复和历史复制；
- package hash 和 rules SHA-256；
- 原子写入；
- `rule_selection={version,sha256}` 固定 draft/finalize 快照。

AI 候选只能进入草稿，不能自动发布。`0.55/0.47` 仍待业务负责人批准，
不得描述为正式生产阈值。

## 当前状态

- 内部 repository/service：已存在；
- 私有规则快照加载：已存在；
- 当前规则公开查询：尚未接入；
- `run_management.bat manage`：尚未接入规则治理操作；
- TaskService 自动固定快照：等待统一合同和框架复审；
- manifest capability：尚未声明；
- 框架页面：尚未接入；
- 合并前置：是，必须先批准统一 FCR。

本文件不得再用于绕过统一合同复审。
