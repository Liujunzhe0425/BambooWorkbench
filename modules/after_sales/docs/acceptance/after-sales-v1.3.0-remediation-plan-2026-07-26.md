# 售后模块 v1.3.0 中央合同整改计划

日期：2026-07-26
分支：`module/after-sales`
模块：`after_sales`
目标版本：`1.3.0`
依据：`docs/acceptance/rectification/after-sales-v1.3.0-2026-07-26.md`
当前基线：售后提交 `8daeadf` 已合并本地 `integration@460a29b`，合并提交为 `63bdb28`

## 1. 整改目标

保留售后 v1.3.0 已完成的月度快照、年度累计、人工复核、Excel、Word、图表和离线安全内核，通过薄适配接入框架已经发布的中央 v1.3 月度合同。

整改完成后，售后模块必须能够：

1. 接受中央 JobRequest 的任务名称、目标年月和学习开关字段。
2. 通过 manifest 完整声明月度累计和学习 Schema。
3. 在 finalize 顶层返回当前任务目标月份的 `monthly_snapshot`。
4. 在 `ConfirmationPrompt.learning` 中直接返回公共学习描述。
5. 按中央累计请求和响应 Schema 执行 `rollup`。
6. 在源码、便携运行时和正式 TaskService 链路中保持一致行为。
7. 保持售后 AI 服务优先流程只调用一次，finalize 和 rollup 均不重复联网。

## 2. 范围与边界

### 2.1 允许修改

只修改：

- `modules/after_sales/module.json`
- `modules/after_sales/schemas/`
- `modules/after_sales/src/after_sales_agent/`
- `modules/after_sales/tests/`
- `modules/after_sales/README.md`
- `modules/after_sales/CHANGELOG.md`
- `modules/after_sales/docs/`
- 售后模块自身的便携运行时构建或入口脚本

### 2.2 禁止修改

- 不修改 `contracts/`、`core/`、`ui/`、`app/` 和仓库级框架测试。
- 不修改 `integration` 或 `main`。
- 不修改水分、水煮或 Mock 模块。
- 不读取、保存或内置 API Key、Provider 凭据和授权 Header。
- 不把内部快照或学习旁路文件登记为普通用户成果。
- 不改变售后费用、责任工厂、投诉类型及其他既有业务口径；如发现必须调整，先单独说明并补充业务验收证据。

## 3. 已确认差异

| 区域 | 当前实现 | 中央合同要求 | 整改方向 |
|---|---|---|---|
| Manifest | 只有 `capabilities: ["monthly_rollup"]` | 必须有完整 `monthly_rollup` 对象，并在使用学习描述时声明 `learning_schema` | 补齐入口及四个 Schema 路径 |
| JobRequest | 白名单拒绝 `task_name`、`period_year`、`period_month`、`learning_enabled` | 中央 TaskService 会传入上述字段 | 接受、校验并在 finalize 使用目标年月 |
| Finalize 快照 | 可按记录月份生成多个快照和旁路目录 | 一个根任务只返回目标年月的单个顶层 `monthly_snapshot` | 按 JobRequest 目标年月筛选并写入单个内部快照 |
| 学习描述 | 写入 `after_sales_learning_descriptors.json` | 学习对象必须进入 `ConfirmationPrompt.learning` | 直接映射到确认项，删除普通成果旁路依赖 |
| 累计请求 | 使用 `request_id`、`staging_output_dir` 和三个独立配置 ID | 使用 `transaction_id`、`snapshot_root`、`output_dir`、`configuration_identity` 等中央字段 | 在累计入口增加中央薄适配 |
| 累计响应 | 使用 `errors[]`、旧快照哈希结构 | 使用稳定 `error {code,message}`、`network_call_count=0`、`record_count`、快照 ID/SHA 和成果 SHA | 重构成功及失败响应外壳 |
| 快照校验 | 校验月份、路径和 SHA，缺少中央快照身份/大小字段处理 | 必须确认 snapshot ID、模块、年月、大小、SHA、路径根和顺序 | 保留现有安全内核并补齐中央字段 |
| 端到端链路 | 模块自身测试可通过，正式 TaskService 新字段失败 | Registry → TaskService → Runner → BAT 必须完整通过 | 增加模块内真实框架链路测试 |

## 4. 实施步骤

### 阶段 A：建立失败基线和合同锁定

1. 运行现有售后模块完整测试、Ruff、合同 CLI、version 和 self-check，记录当前失败。
2. 使用中央 Schema 构造最小 JobRequest、月度累计请求和响应夹具。
3. 增加合同锁定测试，先稳定复现以下失败：
   - manifest 缺少完整 `monthly_rollup`；
   - JobRequest 新字段被拒绝；
   - finalize 缺少顶层 `monthly_snapshot`；
   - confirmation 缺少顶层 `learning`；
   - 中央 Runner 请求无法被旧累计解析器接受。

完成标准：失败原因与整改说明一致，没有混入售后业务计算失败。

### 阶段 B：补齐 Manifest 和模块自有公共 Schema

1. 在 `module.json` 增加：
   - `monthly_rollup.schema_version`
   - `monthly_rollup.entrypoint`
   - `monthly_rollup.snapshot_schema`
   - `monthly_rollup.request_schema`
   - `monthly_rollup.response_schema`
   - `monthly_rollup.learning_schema`
2. 将累计响应文件名统一为中央约定的 `monthly-rollup-result.schema.json`。
3. 更新请求和响应 Schema，使字段结构与中央 Schema 一致，同时保留售后模块的更严格业务约束。
4. 新增 `confirmation-learning.schema.json`，约束：
   - 稳定 `learning_key`；
   - 仅允许批准的投诉类型候选；
   - 上下文只包含稳定、脱敏的品牌组和产品组；
   - 禁止客户、姓名、电话、地址、文件名、路径和原始单元格。
5. 保持 `monthly-snapshot.schema.json` 为模块自有 payload 合同，并补齐中央快照身份所需字段。

完成标准：静态合同 CLI 退出码为 0，所有 Schema 路径真实存在、位于模块目录内且不是链接。

### 阶段 C：适配中央 JobRequest

1. 在 `cli.py::_validate_job` 白名单中接受：
   - `task_name`
   - `period_year`
   - `period_month`
   - `learning_enabled`
2. 增加确定性校验：
   - 年份符合中央范围；
   - 月份为 1—12；
   - `task_name` 和 `learning_enabled` 类型正确；
   - draft 与 finalize 的目标年月一致。
3. 保持所有任务路径必须为绝对路径，保持 finalize 对 `parent_job_id`、确认文件和服务响应文件的既有约束。
4. 对旧框架未提供新字段的普通任务保持兼容；但进入月度正式流程时目标年月必须明确。

完成标准：中央 JobRequest 可通过模块解析，非法年月和未知字段仍返回稳定、可理解的错误。

### 阶段 D：改造 finalize 单月快照

1. 将现有“按记录自动生成一个或多个月份快照”改为“按 JobRequest 目标年月生成一个快照”。
2. 只允许纳入：
   - 属于目标年月的正式记录；
   - 已完成售后费用人工确认；
   - 已完成责任工厂人工确认；
   - 已完成投诉类型人工确认；
   - 已完成整条人工复核。
3. 快照只保存累计必需的脱敏结构化最终值，不保存客户原文、原始单元格、绝对输入路径或 Provider 数据。
4. 将快照登记到 `result.json` 顶层：

```json
{
  "monthly_snapshot": {
    "schema_version": "1.0",
    "path": "<absolute-output-path>",
    "snapshot_format": "module-owned-v1",
    "year": 2026,
    "month": 7
  }
}
```

5. 快照文件不进入普通 `outputs`。
6. draft 不返回正式快照；finalize 失败或确认不完整时不得伪造快照。
7. 明确处理输入中包含非目标月份记录的策略：保留普通单批分析结果，但只将目标年月正式记录写入本次月度快照，并对被排除记录提供稳定诊断。

完成标准：中央 Runner 能校验并接管单个月度快照，快照内容与人工最终答案逐条一致。

### 阶段 E：映射公共 LearningDescriptor

1. 修改确认项归一化流程，将投诉类型的学习描述直接写入对应 `ConfirmationPrompt.learning`。
2. 学习对象对齐中央字段：
   - `schema_version`
   - `learning_key`
   - `field`
   - `context`
   - `context_levels`
   - 稳定候选 ID 与显示文本
   - `base_suggestion_id`
   - `preference_adjustable`
3. `learning_enabled=false` 时仍可返回描述供合同校验，但框架不得激活学习证据；模块不得自行持久化权重。
4. 费用为数值、责任工厂为自由文本时不擅自声明可学习；只为适合枚举学习的投诉类型返回描述。
5. 停止依赖 `after_sales_learning_descriptors.json`；如为旧测试兼容暂时保留文件，必须确保它不进入普通 outputs，并在本轮结束前决定删除或明确标记为非公共兼容文件。

完成标准：中央和模块 learning Schema 均通过，确认页建议仍可编辑，最终业务值仍只来自人工答案。

### 阶段 F：适配中央累计请求

1. 累计入口接受并校验：
   - `transaction_id`
   - `module_id`
   - `module_version`
   - `year`
   - `target_month`
   - `snapshots`
   - `snapshot_root`
   - `output_dir`
   - `configuration_identity`
   - `offline_required`
2. 每个快照项确认中央 snapshot ID、月份、路径、大小和 SHA-256。
3. 所有快照路径必须位于 `snapshot_root` 内，并继续拒绝：
   - 非普通文件；
   - 符号链接、junction 和其他重解析点；
   - 路径越界；
   - 哈希或大小不一致；
   - 跨模块、跨年、重复月份、乱序及目标月之后的快照。
4. 允许月份缺口。
5. `output_dir` 必须为框架授权目录；模块只在其中写入累计成果，不自行发布正式结果。
6. 保留当前售后累计业务内核，不重新解析原始 Excel，不请求人工确认，不调用 AI。

完成标准：中央 MonthlyRunner 能直接调用 `run_module.bat rollup`，无需框架针对售后做私有字段转换。

### 阶段 G：适配中央累计响应

1. 成功响应原样返回并确认：
   - `transaction_id`
   - 模块和版本
   - 年份和目标月份
   - `status`
   - `used_months`
   - 快照 ID/SHA 集合
   - `record_count`
   - 全部成果及 SHA-256
   - `network_call_count: 0`
2. 每个成果路径必须位于 `output_dir` 内，SHA-256 在文件完全写入后计算。
3. 失败响应统一为单个稳定 `error {code,message}`，不再使用 `errors[]`。
4. 响应通过临时文件和原子替换写入 `--response` 指定路径。
5. stdout 只输出 ProgressEvent JSON 行；诊断进入 stderr。
6. 错误消息不得包含 traceback、绝对路径、环境变量、客户内容或凭据。

完成标准：中央 Runner 对成功和失败响应均能完成 Schema、路径和哈希复验。

### 阶段 H：AI、离线与兼容性复验

1. 验证已成功测试且 revision 未变化的全局 AI 配置可跳过售后设置页。
2. 验证每个售后任务仍单独询问一次本批次联网授权；拒绝时框架不创建任务。
3. 验证服务优先流程：
   - 第一次 draft 生成脱敏请求；
   - 框架只执行一次 Provider 调用；
   - 第二次 draft 绑定响应并生成业务确认；
   - finalize 复用响应且服务请求数为 0。
4. 验证 AI 超时、拒绝、非法响应和缺失响应均安全降级，不丢失输入对账。
5. 在 rollup 测试中阻断 socket、HTTP、代理和凭据读取；累计仍成功且 `network_call_count=0`。
6. 确保源码入口、冻结 EXE、便携运行时和 BAT 失败码一致。

完成标准：AI 调用次数、授权行为和零联网证据可机读并可重复验证。

## 5. 测试矩阵

| 类别 | 必测场景 |
|---|---|
| Manifest/Schema | 合同完整、Schema 存在、非链接、模块内路径、中央与模块双重校验 |
| JobRequest | 新字段通过、旧任务兼容、非法年月、类型错误、未知字段、draft/finalize 年月一致 |
| Finalize | 单月快照、人工最终值、确认缺失、目标月过滤、无敏感字段、快照不进入 outputs |
| Learning | 稳定键、稳定候选、层级顺序、脱敏上下文、非法敏感键拒绝、费用/责任工厂不误学习 |
| 累计正常路径 | 单月、连续多月、1+3 月缺口、零记录边界、早期月份替换后重算 |
| 累计错误路径 | 跨年、重复、乱序、越界、snapshot ID 不符、大小不符、输入 SHA 不符、输出 SHA 不符 |
| 文件安全 | snapshot_root 越界、output_dir 越界、相对路径、符号链接、junction、重解析点、非普通文件 |
| AI | 单次服务调用、拒绝不建任务、任务中故障降级、finalize/rollup 不重复调用 |
| 输出 | 累计台账、Word、品牌图、原因图、费用图、年度看板、结构化记录全部可打开 |
| 运行环境 | 源码、BAT、便携冻结运行时、无系统 Python 环境 |
| 质量门禁 | 模块完整测试、Ruff、合同 CLI、version、self-check、`git diff --check` |

## 6. 建议测试文件调整

优先修改或新增：

- `tests/test_contract_adapter.py`：中央 JobRequest、顶层 monthly snapshot、公共 learning。
- `tests/test_monthly_rollup.py`：中央累计请求/响应、哈希、路径和替换场景。
- `tests/test_task_service_integration.py`：Registry → TaskService → Runner → BAT 完整链路。
- `tests/test_ai_service.py`：服务调用次数和 finalize 复用。
- `tests/test_acceptance_regressions.py`：人工最终值、输出可打开、旁路成果清理。
- 新增中央 Schema 锁定测试，避免模块合同再次漂移回 FCR 草案。
- 新增便携累计入口测试，验证无系统 Python 时的中央请求和响应。

## 7. 执行顺序与提交建议

建议按以下顺序实施，避免业务改动和合同改动混杂：

1. `test(after-sales): lock central v1.3 contracts`
2. `fix(after-sales): accept central monthly job fields`
3. `fix(after-sales): publish monthly snapshot and learning`
4. `fix(after-sales): adapt central rollup request and result`
5. `test(after-sales): cover task service portable and offline flows`
6. `docs(after-sales): record v1.3 remediation evidence`

每个提交必须只包含售后模块目录，且能够单独说明目的和回滚影响。

## 8. 交付物

重新交付前应准备：

1. 更新后的 `module.json` 和四个模块 Schema。
2. JobRequest、finalize、learning、rollup 薄适配实现。
3. 完整自动化测试及脱敏夹具。
4. 源码与便携运行时验证结果。
5. AI 单次调用和累计零联网证据。
6. 更新后的 README 和 CHANGELOG。
7. 新的整改测试证据文档，列明命令、退出码、通过数和已知限制。
8. Draft PR #67 的最新 SHA、修改清单、测试结果和框架重点复验接口。

## 9. 完成判定

以下条件全部满足才视为整改完成：

- 只修改 `modules/after_sales/`。
- 中央合同 CLI 退出 0。
- Registry → TaskService → Runner → BAT 完整通过。
- finalize 只返回目标年月的顶层单月快照。
- 投诉类型学习描述进入 `ConfirmationPrompt.learning`。
- 累计请求和响应完全符合中央公开 Schema。
- 累计使用最终人工值，且 AI/网络/凭据访问次数为 0。
- 所有成果在源码和便携环境均可打开。
- 模块完整测试、Ruff、version、自检和 `git diff --check` 全部通过。
- README、CHANGELOG 和测试证据与实际实现一致。
- 只更新目标为 `integration` 的 Draft PR #67，不创建指向 `main` 的 PR。

## 10. 风险与回滚

- **合同漂移风险**：以仓库中央 Schema 和 `core.contracts` 模型为唯一事实来源，通过 Schema 锁定测试防止再次采用 FCR 草案字段。
- **业务回归风险**：累计业务内核保持不变，优先在输入/输出边界增加适配，不重写费用和分类计算。
- **学习污染风险**：只开放投诉类型枚举学习，敏感上下文和自由文本字段默认拒绝。
- **月度污染风险**：finalize 只按任务目标年月生成快照，普通分析结果与正式月度快照明确分离。
- **路径安全风险**：继续采用包含性、哈希、普通文件和重解析点多重校验。
- **便携差异风险**：源码和冻结入口使用同一合同测试夹具。
- **回滚方式**：按上述独立提交逆序撤销薄适配；不删除数据库、不修改框架合同、不影响 v1.2.1 Excel 兼容修复及 v1.2.0 AI 基线。
