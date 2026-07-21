# 竹丝水分模块迁移行为不变量

## 1. 用途与裁决顺序

本文件冻结迁移期间不得因重构、合同适配或测试修复而改变的行为。发生冲突时按以下顺序裁决：

1. `contracts/schemas/module-manifest.schema.json`
2. `contracts/schemas/job-request.schema.json`
3. `contracts/schemas/module-result.schema.json`
4. `contracts/examples/`
5. BambooWorkbench 主框架真实代码
6. 主框架最终交接、模块开发指南和验收清单
7. 已批准的新架构与重构实施计划
8. 旧提交 `d98433b` 的 Task 1—9 代码和测试
9. 旧架构及 Task 10

机器 Schema 不因旧测试或旧实现而修改。框架缺陷只记录，不在模块分支修复。

### 1.1 旧证据范围与业务批准状态

本文件引用的旧证据只来自只读提交
`d98433b489feafea7e19b0a4392e11a25c6b31b2` 的 Task 1—9。旧代码、旧测试、
旧 `published` 字段和旧报告文案只能证明历史行为，不能证明客户已经批准业务口径。

截至 T01：

- 高阈值 `0.55`、低阈值 `0.47` 及“竹丝/原竹丝”材料范围已由负责人于
  2026-07-17 批准；运行规则为 `confirmed`，但只表达筛查疑似。
- 公式和统计口径已由负责人于 2026-07-17 批准为当前迁移基线；继续以旧数值测试
  发现迁移漂移。
- 供应商与部门采用已批准的保守治理方式；不得根据文件名、旧 fixture 或历史经验
  擅自固化映射，有歧义时生成 confirmation。
- 结构化辅助证据资格和四种颜色展示语义已批准为受限复核提示；正式错误和责任流程
  仍明确不属于模块。
- 橙/绿=`info`、红/蓝=`warning` 由正式重构实施计划冻结。批准架构第 13 节中残留的
  橙/绿=`warning`、红/蓝=`critical` 旧映射与正式计划冲突时不采用；v0.1.0 不为颜色
  状态使用 `critical`。

批准记录只覆盖上述筛查和辅助语义；不得扩张为正式不合格、责任或处置标准。

## 2. 进程和外部合同不变量

1. 正式模块只位于 `modules/moisture/`，由主框架以独立子进程启动。
2. 外部接口仅为 `module.json`、`run_module.bat`、`version`、`self-check`、`run --job`、协议文件、stdout JSON Lines、stderr、退出码和 output artifacts。
3. 模块不 import 主框架内部 Python 代码，不共享 DTO、数据库、回调或 HTTP 服务。
4. `supports_incremental=false`，`requires_network=false`。
5. stdout 只允许版本输出或 `ProgressEmitter` 的 JSON Lines；日志与 traceback 只进入 stderr。
6. 模块不依赖当前工作目录，不硬编码开发机绝对路径。
7. 所有输入与输出路径先 resolve，再验证位于 job 授权范围。

## 3. 输入、身份和完整性不变量

1. 只处理 job 明确列出的 `.xlsx` 输入副本；不扫描用户磁盘。
2. 文件名以 `~$` 开头的 Excel 临时文件必须跳过。
3. 文件内容身份使用 SHA-256；绝对路径、output_dir、执行时间和随机 UUID 不参与业务身份。
4. 内容完全相同的多个文件只计算第一次出现的文件，其余形成稳定的 info/skipped 记录。
5. 原始输入处理前后 SHA-256 必须一致；读取中发生变化时该文件失败。
6. 模块不得修改、重命名、移动或删除输入文件。
7. 单文件失败不得无故终止其他输入；至少一份成功且一份失败时为 `partial_success`。

旧证据锚点：`tests/integration/excel/test_source_parser.py` 中源文件不变、读取后复核 hash、解析错误与修改冲突测试。新证据目标：T08、T09、T14。

## 4. 工作簿和样本识别不变量

1. 每个工作簿动态识别 1—10 个有效样本，不固定为 6 个。
2. 超过 10 个有效样本时整个文件失败，绝不静默截断。
3. 工作表、表头、部门、部门样本数和来源单元格动态识别。
4. 多个工作表得分相同且无法唯一确定时，返回结构化歧义；draft 可据此生成业务 confirmation。
5. 已唯一识别的 sheet、表头和值不得要求用户重复输入。
6. 缺字段、损坏 workbook 和格式变化必须形成文件级结构化结果，不泄漏库 traceback 到 stdout。

旧证据锚点：`test_parser_accepts_supported_sample_counts`、`test_parser_reads_dynamic_departments_and_six_samples`、`test_parser_rejects_eleven_samples_without_truncation`、`test_parser_detects_shifted_header_on_non_default_sheet`、`test_parser_rejects_tied_valid_worksheets`。新证据目标：T09、T15。

## 5. 公式和 Decimal 统计不变量

1. 源表含水率必须读取，同时根据源始末重量独立复核公式。
2. 原值、复核值和最终统计采用值分别保留，不能用写回 Excel 的方式“修正”原值。
3. 业务计算和阈值比较使用 `Decimal`；不得为方便序列化而提前转为 float。
4. 统计至少保持：最大值、最小值、区间、均值、标准差、中位数、四分位数、IQR 和部门均值最大差。
5. 统计算法迁移以旧通过测试为基线，不为重构而重写口径。

旧证据锚点：`tests/unit/domain/test_formula_verification.py`、`test_statistics.py`。新证据目标：T07。

## 6. 规则治理和初筛不变量

1. 规则必须包含编号、版本、来源、适用范围、规则文件 hash 和客户确认状态。
2. 只有 `confirmed` 规则可自动判定；`pending_confirmation` 规则只能生成确认或说明。
3. 规则包运行时只读；runtime 目录只包含 `rule-package.json` 和 `rules.yaml`。
4. expected results 只位于 `tests/fixtures/rule_packages/`，不得进入 runtime rules。
5. evaluator registry 是新增规则类型的唯一窄扩展点；不建设通用插件平台或运行时发布服务。
6. 旧默认阈值未获得客户确认前必须保持 pending，不能因旧测试存在而升级为正式标准。

旧证据锚点：`tests/unit/rules/test_evaluators.py`、`tests/integration/rules/test_local_repository.py`、`tests/unit/rules/test_lifecycle.py`。新证据目标：T10。

## 7. 颜色与异常语义不变量

| Review state | 显示色 | 色值 | 合同 severity | 业务含义 |
|---|---|---|---|---|
| `normal` | 无 | — | — | 未命中初筛疑似 |
| `suspect_high` | 橙 | `F4B183` | `info` | 确定性规则发现偏高疑似 |
| `suspect_low` | 绿 | `A9D18E` | `info` | 确定性规则发现偏低疑似 |
| `high_suspicion_high` | 红 | `FF0000` | `warning` | 有效辅助证据支持的高度偏高疑似 |
| `high_suspicion_low` | 蓝 | `5B9BD5` | `warning` | 有效辅助证据支持的高度偏低疑似 |

红蓝仍不是正式错误、不合格或责任结论；v0.1.0 不为颜色状态使用 `critical`。无有效服务/经验依据时必须保留橙绿。

旧证据锚点：`tests/unit/domain/test_review.py`、`tests/integration/ai/test_ai_review.py` 中颜色与降级断言。新证据目标：T11、T19。

## 8. confirmations 不变量

1. 只为水分解释、年份/sheet 歧义、供应商/部门映射、公式冲突和 pending 规则适用性生成确认。
2. 不生成身份、密码、Provider、网络、API Key 或“责任结论”确认。
3. 可确定性读取或计算的 Excel 内容不生成确认。
4. draft 根身份为当前 `job.job_id`；finalize 根身份为 `job.parent_job_id`。
5. 稳定 confirmation ID 为 `msr-confirm-<SHA256前24位>`，不得依赖 finalize 自身 job_id、绝对路径、时间或 UUID。
6. draft 存在模块业务 confirmations 时模块原始状态为 `needs_confirmation`。
7. finalize 只重建并应用 draft 确认，不生成新 confirmation。

新证据目标：T15、T18。

## 9. service requests 与经验/AI 不变量

1. 模块只声明服务需求，不直接调用知识库或 AI Provider。
2. 每个 job 最多一个 knowledge request 和一个 AI request；二者只在 draft 产生。
3. knowledge request 的 `requires_user_consent=false`；允许 scope 优先 `moisture`，其次 `shared`；query 不超过 200 个 UTF-8 字符。
4. AI request 的 `requires_user_consent=true`；`ai_enabled=false` 表示尚未授权，不禁止模块声明业务需要。
5. 每个 AI request 最多 50 个候选；规范化 JSON payload 不超过 65,536 UTF-8 字节。
6. 候选按相对偏离度降序、同分 candidate_id 升序；超限从末尾移除；未发送候选保持橙/绿。
7. request ID 使用 root_job_id、module_id、服务类型、规则 hash 和排序后候选摘要 hash；不得使用 finalize 当前 job_id。
8. payload 不包含完整 Excel、绝对路径、客户身份、原始行、API Key 或无边界历史。
9. 普通知识文本只能作报告引用；只有通过结构化经验 Schema 校验的已审核记录才可能参与复判。
10. v0.1.0 不实现 knowledge→AI 多轮调用。

旧证据锚点：`test_gateway.py` 中最小 payload、证据绑定、禁止责任结论和预算思想；Provider/HTTP 重试测试明确不迁。新证据目标：T12、T16、T17。

## 10. 服务响应与离线降级不变量

1. 只有 request ID、rule hash、candidate ID、direction、field、observed value 全部匹配，decision 合法、evidence 非空且 `confidence >= 0.80` 时，AI 证据才可提升红蓝。
2. `denied`、`error`、`timeout`、missing、invalid envelope、非法业务 JSON 和 MockProvider 普通文本均保留橙绿。
3. 服务失败通过顶层 errors、analysis_summary 和“模型分析记录”呈现，不自动把基础 success 改为 partial_success。
4. 服务降级不得丢失已完成的本地确定性统计和 artifacts。
5. finalize 不发起第二轮请求或确认。

旧证据锚点：`tests/integration/ai/test_ai_review.py` 中稳定降级、证据精确绑定、方向不匹配、低置信度和异常隔离测试。新证据目标：T19。

## 11. draft/finalize 状态不变量

确定性基础状态：

- 所有可处理文件成功：`success`
- 至少一份成功且至少一份失败：`partial_success`
- 无任何可用业务结果：`failed`

draft 裁决：

1. 基础状态为 failed 时保持 failed，不为调用服务制造请求。
2. 有模块业务 confirmations 时为 `needs_confirmation`。
3. 无模块 confirmations、仅有 service_requests 时保持基础 success/partial_success。
4. `confirmation_count` 只统计模块生成的 prompts；宿主注入的 AI 授权项由宿主负责。
5. knowledge-only 可由框架自动 finalize；AI consent 等待态可由宿主规范化。

finalize 裁决：

1. 重新执行与 draft 相同的确定性管线，不依赖 draft 内存或隐藏数据库。
2. `result.job_id` 使用当前 finalize `job.job_id`；稳定业务 ID 使用 `parent_job_id`。
3. finalize 输出的 confirmations 和 service_requests 必须为空。

新证据目标：T14—T19。

## 12. 条件协议文件不变量

1. `confirmation_file` 仅在 draft 产生模块业务 ConfirmationPrompt 或 `requires_user_consent=true` 的 AI request 时必需。
2. 无确认需求时允许该字段为 null；当前框架若提供空 bundle，模块接受并校验。
3. confirmation bundle 的 job_id 必须等于 root_job_id。
4. `service_response_file` 仅在重建出的 draft service_requests 非空时必需。
5. 有请求但 service file 缺失、不可读或非法时，为预期请求产生降级记录，不丢失确定性成果。
6. 无服务请求时意外提供 service file 不得改变结果。

新证据目标：T06、T18、T19。

## 13. 状态与退出码不变量

状态只能由集中 mapper 计算，CLI、orchestrator 和 writer 不各自维护一套规则。

| 情况 | 状态/退出码 |
|---|---|
| 合法 success/partial/needs_confirmation/cancelled result | exit 0 |
| 合法 failed result | exit 0 |
| 非法 CLI、job JSON 或任务合同 | exit 2 |
| 内部崩溃或无法形成/写入合法 result | exit 3 |
| 依赖、模板、规则包或运行环境缺失 | exit 4 |

业务失败不等于进程失败。

## 14. 规则包变化不变量

draft/finalize 规则 hash 不一致时：

- `status="failed"`，退出码 0；
- `outputs=[]`、`confirmations=[]`、`service_requests=[]`；
- 顶层 errors 包含 `RULE_PACKAGE_CHANGED_DURING_TASK: active rule package does not match draft-bound identities`；
- analysis_summary 记录当前规则版本/hash、无法复现的 ID 类型和重新创建任务建议；
- 可处理输入的 FileResult 为 failed，错误码 `RULE_PACKAGE_CHANGED_DURING_TASK`；
- 不伪装为颜色 anomaly。

新证据目标：T19。

## 15. artifacts 与原子输出不变量

正式 artifacts：

- `moisture_summary.xlsx`
- `analysis_report.md`
- 最后写入的协议文件 `result.json`

XLSX 必须包含：

- `竹丝含水率统计`
- `异常分析明细`
- `趋势分析`
- `来源追溯`
- `模型分析记录`

固定写入顺序：

1. output_dir 内写临时 XLSX；
2. 关闭并校验后 `os.replace` 为正式 XLSX；
3. output_dir 内写临时 Markdown；
4. 校验并原子替换为正式 Markdown；
5. 只登记真实存在且位于 output_dir 的正式 artifacts；
6. 构造并用受锁 Schema 副本校验 ModuleResult；
7. flush/fsync 临时 JSON 后 `os.replace` 为 `result.json`；
8. result 成功后才发出 100% progress。

result 写入失败时退出 3；半成品不得被 result 引用或被框架登记。

旧证据锚点：`tests/integration/output/test_summary_writer.py`、`test_markdown_writer.py`、`test_result_writer.py`。新证据目标：T05、T11、T13、T14。

## 16. 禁止能力不变量

迁移后仍不得出现：

- GUI、FastAPI、Uvicorn 或其他 HTTP 服务；
- Identity、用户、密码、角色、Session、Cookie、CSRF；
- 框架 SQLite、Windows 凭据或 API Key；
- OpenAI/Azure/其他 Provider adapter、HTTPX gateway 或网络重试；
- rules-ui、rules-user、运行时规则写入/发布；
- 旧 JobConfig、旧 Job/Result Schema 或旧 Manifest 能力声明；
- 扫描用户磁盘、修改原始 Excel、越过 output_dir 写入；
- draft 隐藏状态、finalize 新 service_requests；
- 客户原始表、个人路径、密钥和测试缓存进入 Git。

## 17. 迁移验收原则

每项实现都必须按以下顺序证明：旧业务测试意图已识别 → 新目录最小失败测试确实失败 → 只迁最小实现 → 定向测试通过 → diff 未越界。若新机器合同与旧行为冲突，停止冲突迁移并记录，不修改官方 Schema 或主框架。
