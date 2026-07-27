# 水分模块 v1.3.0 人工验收后整改与重新交付说明

基线：`integration@b89d5f4d6ebcff73f386ed791a7a0cb017bf35ab`。旧 PR #65 已合并，本轮必须创建新的 Draft PR。

## 当前问题

真实 2026 年 4 月水分任务共 21 条记录，解析、年份确认和规则身份均正确，但 finalize 写月度快照失败：

```text
ARTIFACT_WRITE_FAILED: MonthlySnapshotError
```

框架诊断复现出 21 项 Schema 错误：模块实际生成的中文业务 `record_id` 不符合私有 Schema 复用的英文版本号正则。

## 问题位置和产生原因

- `schemas/moisture-monthly-snapshot.schema.json`：`record_id` 引用 `$defs/version`，只允许 `[A-Za-z0-9._:-]`；
- `application/monthly_snapshot.py`：快照记录直接使用真实业务记录 ID，可能包含中文、全角括号和空格；
- `finalize_orchestrator.py`：捕获异常后只返回异常类名，稳定错误码被丢失；
- 现有测试主要使用英文/ASCII ID，没有覆盖模块真实会产生的 Unicode ID。

## 责任边界

水分负责人负责私有业务 ID、私有快照 Schema、模块错误映射及模块测试。框架负责人不修改水分解析、公式、阈值、规则或快照业务 payload。

## 整改需求

1. 统一真实业务 `record_id` 的生成规则与私有 Schema：可以定义稳定机器 ID并另存显示名称，也可以定义安全的 Unicode 业务 ID合同，但必须稳定、唯一、可解释。
2. 禁止记录 ID 包含绝对路径、控制字符或路径穿越片段；不得通过接受任意对象或移除唯一性约束来规避验证。
3. finalize 应保留脱敏稳定错误码，例如 `MONTHLY_SNAPSHOT_INVALID`，不得只返回 `MonthlySnapshotError` 类名。
4. 增加真实形态的合成测试：中文、空格、全角括号、相似文件名、重复 ID和非法控制字符。
5. 增加 BAT/CLI 完整测试：draft → 年份确认 → finalize → 顶层 `monthly_snapshot` → 离线 rollup。
6. 合法任务的内部快照仍不得进入普通 outputs；失败任务不得产生正式月份或学习贡献。
7. 将水分模块版本和模块 CHANGELOG 更新为 `1.3.1`，不得修改中央应用版本。

## 必须达到的目标

- 真实形态的 2026 年 4 月中文水分记录可以生成合法内部快照；
- 记录 ID 在重复运行中确定且唯一；
- 非法 ID 安全失败并返回稳定错误，不泄露路径或客户原文；
- 不改变水分 Excel、公式、阈值、颜色、统计口径和人工确认业务规则。

## 验收标准

- 模块完整测试、Ruff、Schema lock、version/self-check、合同 CLI、`git diff --check` 全部通过；
- 新增 Unicode 正向与控制字符/重复 ID负向测试；
- `success` finalize 必须提供可由中央 Runner复验的快照；
- 快照路径位于授权 output_dir，年月、规则版本和 SHA-256 一致；
- 源码和便携模块运行时均通过同一链路；
- 测试和文档不得提交本次人工验收使用的真实客户 Excel、姓名或绝对路径。

## 修改范围限制

仅修改 `modules/moisture/`。不得修改 `app/`、`core/`、`ui/`、`contracts/`、其他模块、integration 或 main。

## 自测要求

至少提供：完整模块测试统计、中央合同 CLI、BAT version/self-check、Unicode 快照测试、离线累计测试、便携入口测试、Ruff 和 diff-check。

## 重新交付步骤

1. 同步最新 integration；
2. 在 `module/moisture-test` 内整改；
3. 创建新的 Draft PR，目标必须为 integration；
4. 框架修复进入 integration 后再次同步并重跑正式链路；
5. 提供 PR 链接、最新 SHA、模块版本 `1.3.1`、修改内容、完整测试结果和重点复验接口。

## 禁止事项

不得更新旧的已合并 PR #65 作为交付，不得指向 main，不得修改框架，不得把客户文件加入 fixture，不得简单删除快照 Schema 校验。

## 给负责人的通知

水分人工验收失败已定位：真实中文业务 record_id 与私有快照 Schema 的英文版本号正则不一致，21 条合法 2026 年 4 月记录因此全部无法写快照。请同步最新 integration，仅在 `modules/moisture/` 内统一稳定业务 ID 与 Schema，保留稳定错误码，并补充 Unicode/重复/非法字符及 BAT 全链路测试。模块版本更新为 `1.3.1`。旧 PR #65 已合并，请创建新的 `module/moisture-test → integration` Draft PR，并提供 PR、SHA、版本和完整测试结果。不要提交本次真实客户文件。

## 给 AI Agent 的执行提示词

严格只修改 `modules/moisture/`。先同步最新 integration，读取 `docs/acceptance/rectification/moisture-post-v1.3.0-2026-07-27.md` 和中央月度合同。复现私有快照 Schema 将中文 record_id 错套 `$defs/version` 的问题，设计稳定、唯一、安全且与真实模块输出一致的 ID合同；保留显示信息但禁止绝对路径和控制字符。让 finalize 返回稳定脱敏错误码，补充 Unicode、全角括号、空格、重复 ID、非法字符以及 draft→确认→finalize→snapshot→rollup 的 BAT/便携测试。将模块版本与 CHANGELOG 更新为 `1.3.1`，不得修改中央版本、业务公式、阈值、框架或其他模块，不得提交真实客户数据。创建新的 Draft PR 指向 integration，并报告 PR、SHA、版本及全部验证结果。
