---
request_id: FCR-moisture-20260724-rule-management-snapshot
module_id: moisture
module_version: 1.0.1
owner: moisture模块负责人
status: proposed
framework_areas:
  - ui
  - management
  - workflow
  - storage
breaking_change: false
required_before_module_merge: false
---

# 框架适配请求：轻量规则管理与任务快照

## 目标

提供“规则草稿、当前有效规则、历史版本”三栏入口，并让框架创建任务时固定模块返回的规则`{version, sha256}`。模块侧已经完成文件式草稿/不可变版本、active指针、命中预览、原子发布、停用、恢复和固定快照运行。

## 最小框架改动

1. 独立规则管理页面通过模块管理进程完成创建/更新/校验/预览/发布/停用/恢复/历史复制；
2. 页面只支持现有RuleDefinition、字段、运算符、Decimal阈值和scope；
3. 发布前显示格式错误、明显重复/阈值冲突及所选标准汇总表的命中数量；
4. 用户明确确认后才允许发布，AI候选只能保存为草稿；
5. TaskService创建moisture任务时读取当前规则身份，并写入模块私有`rule_selection={version,sha256}`；
6. draft与finalize沿用同一私有配置，禁止finalize重新选择当前active规则。

## 固定边界

- 规则包仍由现有Schema、RulePackageLoader和Evaluator校验；
- 已发布版本不可原地修改；切换active使用原子指针；
- 管理目录一旦启用即为权威来源，损坏、缺失或hash不符明确失败；
- 草稿和停用版本不参与新任务；发布新版本不改变已固定的旧任务；
- `0.55/0.47`是否作为正式生产标准仍由业务负责人批准；
- 不支持自由公式、代码、AND/OR新语言、自动阈值发布、多人审批或数据库。

## 验收

- 草稿不影响当前检测，非法字段/运算符被拒绝；
- 发布失败保留旧active，恢复不删除历史版本；
- 命中预览复用标准汇总reader和现有Evaluator；
- 同一任务draft/finalize规则版本/hash及结果一致；
- 新任务使用新active规则；
- 快照缺失、hash不符、active损坏均明确失败且不回退内置规则；
- 正式运行依赖图不包含可写规则管理repository。

## 框架方审核

- 审核结论：待审核
- 实施分支/PR：待填写
