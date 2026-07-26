---
request_id: FCR-boiling-20260726-monthly-rollup-framework
module_id: boiling
module_version: 1.3.0
owner: anyuyu1
status: proposed
framework_areas:
  - contract
  - storage
  - workflow
  - ui
  - packaging
breaking_change: false
required_before_module_merge: true
---

# 框架适配请求：接入水煮月度快照、年度累计和确认学习描述

## 1. 业务目标与使用场景

水煮实验需要把每月最终人工确认后的密度、膨胀率、浸渍剥离、异常、冲突和业务记录保存为不可变月度快照，并使用同年截至目标月份的正式快照生成完整年度累计成果。替换早期月份时，需要重算该月和已有后续月份；任一步失败不得改变旧正式结果。

累计重算只复用快照中的最终值、历史人工开裂检查状态和已有 AI 建议，不得重新调用 AI。适合学习的墙板/栏杆规则缺口确认需要向框架提供稳定、脱敏、结构化学习描述。

## 2. 当前限制

当前 `integration@535b7e7` 的公开合同尚不具备以下信息或流程：

- `job-request.schema.json` 没有 `period_year`、`period_month`、`learning_enabled` 和替换候选身份，模块无法区分用户选择月份与源表检测月份，也无法把冲突交给用户确认。
- `module-result.schema.json` 的确认项 `additionalProperties=false`，不允许设计文档第 13.2 节要求的 `learning` 描述。
- 框架没有月度槽位、不可变快照登记、快照哈希、累计事务、后续月份重算或原子提交服务。
- 框架目前只调用 `run --job`，不会调用模块 v1.3.0 的 `rollup --request --response` 入口。
- 当前模块 manifest Schema 没有专用的快照/累计 Schema 路径字段；模块只能通过 `capabilities` 声明能力，并使用约定的 `schemas/` 路径。
- 任务结果页会把所有 `outputs` 当作用户成果；月度快照和确认学习描述应作为内部工件登记，不应让普通用户直接打开。

## 3. 请求的框架改动

### 3.1 页面与交互

- 创建任务时提供年份、月份、任务名称和学习开关。
- 已有正式月份再次创建时，展示旧正式任务、受影响月份和重算范围，并在用户确认后创建替换候选。
- 历史页按模块和年份展示十二个月槽位；正式结果只指向成功累计事务提交的任务。
- 累计准备、渲染、校验或提交失败时显示明确阶段和错误，旧正式成果保持可用。
- 内部 `monthly_snapshot` 和 `confirmation_learning` 工件不进入普通“打开成果”列表。

### 3.2 接口与合同

1. 在任务公共合同中增加可选且向后兼容的：
   - `period_year`
   - `period_month`
   - `learning_enabled`
   - `candidate_for_job_id`
2. 在确认项中增加可选 `learning` 对象，字段与
   `modules/boiling/schemas/confirmation-learning.schema.json`
   的 `LearningDescription` 一致。
3. 为 manifest 增加可选的月度累计声明对象，建议包含：
   - `snapshot_schema`
   - `rollup_request_schema`
   - `rollup_response_schema`
   - `rollup_command`
4. Finalize 成功后读取 `monthly_snapshot` 内部工件，按模块自有 Schema、年月、大小和 SHA-256 校验并登记。
5. 按设计文档第 9.2 节生成请求，调用：

```text
run_module.bat rollup --request <absolute-request.json> --response <absolute-response.json>
```

6. 使用模块响应 Schema 校验 `used_months`、`snapshot_hashes`、全部输出 SHA-256 和 `network_call_count=0`。
7. 旧模块未声明 `monthly_rollup` 时继续执行 v1.2.0 流程。

模块已提供：

- `schemas/monthly-snapshot.schema.json`
- `schemas/monthly-rollup-request.schema.json`
- `schemas/monthly-rollup-response.schema.json`
- `schemas/confirmation-learning.schema.json`

### 3.3 公共服务、存储与打包

- 按设计建立 `(module_id, year, month)` 唯一正式槽位。
- 快照登记后不可原地修改；保存路径、合同版本、大小、SHA-256、任务和状态。
- 替换候选先在授权暂存目录生成所有受影响月份成果，全部校验后一次数据库事务切换槽位、输出和学习证据。
- 源码、便携版和安装版都必须传递相同请求并调用相同模块命令。
- 框架不得读取水煮快照 `payload` 的业务字段，只校验公共信封并委托模块 Schema 校验。

## 4. 责任边界

- 模块方已经完成：月度快照生成、模块自有 Schema、离线累计入口、缺月累计、候选同月替换、跨年/乱序/重复/哈希/路径校验、完整成果渲染、既有 AI/历史开裂字段保留和零联网证明。
- 等待框架提供：任务年月、正式槽位、快照登记、原子替换事务、累计调用、内部工件隐藏、学习证据生效/撤销和历史页。
- 仍由模块方负责：水煮公式、阈值、等级、人工值落盘、业务累计口径、Excel、图表、报告和结构化输出正确性。
- 需要人工确认：输入年月与源表检测月份冲突，以及替换正式月份和受影响范围。

## 5. 数据、安全与权限

- 模块不读取 API Key，不直接联网；累计请求必须为 `forbid_network=true`，成功响应固定 `network_call_count=0`。
- 快照 payload 和学习上下文不得包含绝对路径、客户原文、自由文本身份或原始单元格内容。
- 框架只允许模块读取 `snapshot_root` 内快照、写入事务授权暂存目录；需要防御路径越界、符号链接和 junction 替换。
- AI 建议只作为人工报告辅助文字，不改变最终人工值、确定性数值、规则、等级或业务状态。

## 6. 兼容性与迁移

- 是否破坏现有合同：否，建议全部新增字段可选，未声明能力的旧模块走原流程。
- 是否兼容当前正式版模块：兼容；水煮普通 draft/finalize 在框架适配前仍可运行。
- 旧任务和历史数据：没有月度快照的旧任务保留普通历史，不自动成为正式月度结果。
- 如果框架尚未升级：模块可生成内部快照并用 CLI 独立复验累计，但不能提供正式月份槽位和原子替换。
- 回滚方式：框架忽略 `monthly_rollup` 能力并停止累计调用；水煮模块回滚到 v1.2.1 时旧普通任务仍可查看，已登记快照只读保留。

## 7. 验收标准

1. 新建 2026 年 1 月水煮任务并 finalize 后，框架登记一个经模块 Schema 验证且 SHA-256 正确的内部月度快照。
2. 已有 1 月后创建 3 月、缺少 2 月时，累计响应 `used_months=[1,3]`，四类完整成果可打开。
3. 2025 与 2026 快照不能进入同一次累计；乱序、重复、越界、路径越界和哈希不一致均在正式状态切换前失败。
4. 替换 1 月时，候选快照替换旧 1 月并重算已有后续月份；任一输出失败时旧月份槽位、旧成果和旧学习证据完全不变。
5. 累计输出保留历史快照已有的人工开裂检查字段和 AI 建议，审计记录及模块响应均显示网络调用次数为 0。
6. 墙板/栏杆规则缺口确认展示模块提供的学习描述；只有正式累计事务成功后学习证据生效，替换或移除后旧证据失效。
7. 源码、便携版和安装版调用同一 `rollup` 合同并得到相同 `used_months`、输出类型和业务记录。
8. 未声明能力的 v1.2.0 模块仍可完成原有 draft/finalize。

## 8. 备选方案与影响

- 已考虑由框架直接合并水煮 JSON/Excel：会越过业务责任边界，无法正确处理最终人工值、规则和历史 AI 建议，因此未采用。
- 已考虑模块自行维护正式月份数据库：会与框架任务历史、原子替换和跨模块隔离重复，且增加数据竞争风险，因此未采用。
- 影响的框架功能：任务合同、确认合同、manifest、任务服务、存储迁移、历史页、成果发布和便携/安装调用。
- 影响其他模块：公共字段保持可选；水分和售后可复用同一公共信封与事务服务，但各自 payload 继续由各模块负责。
- 预计风险：路径替换攻击、事务中断、旧月误覆盖和学习证据重复；必须在正式提交前完成哈希、路径和全事务校验。

## 9. 附件与证据

- 脱敏测试：`modules/boiling/tests/test_monthly_rollup.py`
- 模块自有合同：`modules/boiling/schemas/`
- 业务说明：`modules/boiling/README.md`
- 相关设计：`docs/superpowers/specs/2026-07-26-bambooworkbench-v1.3.0-design.md` 第 9、10、13、17.3、18、19 节

## 10. 框架方审核（由框架负责人/Codex填写）

- 审核结论：
- 判断理由：
- 实施分支/PR：
- 验证范围：
- 对模块交付的后续要求：
