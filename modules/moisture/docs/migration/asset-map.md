# 竹丝水分旧项目资产迁移清单

## 1. 审计基线与覆盖证据

- 旧仓库只读来源：`D:\codexprogram\竹丝水分检测`。
- 固定提交：`d98433b489feafea7e19b0a4392e11a25c6b31b2`（`docs: record experience llm and review checkpoint`）。
- 固定命令：`git -C <旧仓库> ls-tree -r --name-only d98433b489feafea7e19b0a4392e11a25c6b31b2`。
- 全树共 113 个文件：本清单逐项审计 46 个 `moisture/src/**` 运行文件、24 个 `moisture/tests/**` 测试/fixture 文件和 14 个模块包资产，共 84 项；其余为 21 份客户原始 XLSX 和 8 份仓库说明/图片/忽略文件。
- 每个下表条目均通过 `git show d98433b:<path>` 读取；Python 文件另以只读 AST 提取顶层符号、imports、显式 raises 和测试函数。未 checkout、未修改旧仓库。
- T01 开始时两份文档已作为用户未跟踪草稿存在，计划中的 `Test-Path ...\asset-map.md` 初始 `False` 已无法原样复现，且未通过删除用户文件伪造红灯。替代的严格逐路径覆盖校验初始结果为 `required=84, covered=1, missing=83`，非零退出；主要遗漏为完整旧路径、包 `__init__.py`、conftest、CLI/package/schema 及 Provider 禁止项的逐文件处置。
- Task 来源按旧历史固定为：Task 1 合同外壳、Task 2 领域/公式、Task 3 Excel parser、Task 4 统计/初筛、Task 5 规则治理、Task 6 输出、Task 7 经验库、Task 8 LLM gateway、Task 9 AI review。稳定提交中尚无 Task 10 Web/Identity 文件。
- 本清单仅作处置和测试路由，不复制实现、不合并旧 Git 历史、不证明业务口径已批准。

处置词义：

- **保留并适配：** 先迁旧业务测试意图，再迁最小实现；名称、依赖和公开边界按新架构调整。
- **仅提取：** 只重建与新职责相符的纯业务语义、校验或安全性质，不复制旧组件。
- **仅测试：** 不进入运行时，只重建为 fixture/helper/回归证据。
- **按需重建：** 只在未来 Task 首次需要包结构时创建空包或元数据，不复制旧文件。
- **不迁移：** 与独立模块职责冲突、由宿主负责、属于旧合同/客户数据，或是运行时管理能力。

## 2. 业务批准状态（T01 人工核对入口）

| 项目 | 当前状态 | T01 约束 |
|---|---|---|
| 高阈值 `0.55`、低阈值 `0.47` 及材料/季节/供应商/日期适用范围 | **待业务/客户批准** | 旧 `default_rules.yaml` 的 `published` 和旧测试通过都不是客户批准证据；新规则只能 `pending_confirmation`，不得自动作正式标准。 |
| 公式与统计口径 | **待业务/客户批准** | T07 先保持旧测试基线以防迁移漂移，但不得写成“已批准口径”。 |
| 供应商与部门映射 | **待业务/客户批准** | parser 只能保留 raw/normalized 值和歧义；未经确认不得固化映射。 |
| 橙/绿与红/蓝 severity | **由正式实施计划冻结** | 橙/绿=`info`，红/蓝=`warning`；批准架构 §13 的旧 `warning/critical` 映射不再采用。颜色仍不是不合格或责任结论。 |
| 客户最终展示文案、结构化经验提升资格、正式责任流程 | **待业务/客户批准** | 不从旧模板、旧 AI 输出或测试推导批准状态。 |

## 3. 运行文件逐项处置：包、领域与基础设施

表中“边界”依次记录旧输入 → 旧输出；显式异常。依赖只列直接的关键依赖。所有“保留/提取/重建”条目均给出目标、旧测试与未来测试以及实施 Task。

| 旧运行文件（主要符号） | 处置 | 旧边界；异常；依赖 | 新目标 | 旧测试 → 未来测试 | Task / 适配 |
|---|---|---|---|---|---|
| `moisture/src/moisture/__init__.py`：`MODULE_ID`、`MODULE_VERSION` | 仅提取 | import → 旧标识/版本；无；无 | `modules/moisture/src/moisture/__init__.py` | `moisture/tests/unit/test_cli.py` → `modules/moisture/tests/contract/test_cli_health.py` | T02；值按正式 manifest 重建。 |
| `moisture/src/moisture/adapters/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/adapters/__init__.py` | `moisture/tests/integration/excel/test_source_parser.py` → `modules/moisture/tests/integration/excel/test_source_parser.py`（其余 adapter 由各 Task 定向测试覆盖） | T09/T10/T12；不整目录复制。 |
| `moisture/src/moisture/application/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/application/__init__.py` | `moisture/tests/integration/ai/test_ai_review.py` → `modules/moisture/tests/integration/test_deterministic_pipeline.py` | T14；不携带旧服务注册。 |
| `moisture/src/moisture/domain/enums.py`：四组状态/颜色枚举 | 保留并适配 | 枚举值 → 领域状态；无；`enum.StrEnum` | `modules/moisture/src/moisture/domain/enums.py` | `moisture/tests/unit/domain/test_models.py`、`moisture/tests/unit/domain/test_review.py` → `modules/moisture/tests/unit/domain/test_models.py`、`modules/moisture/tests/unit/domain/test_review_state_applier.py` | T07/T19；合同 severity 由 mapper 集中决定。 |
| `moisture/src/moisture/domain/errors.py`：`MoistureDomainError` | 保留并适配 | 领域错误消息 → typed error；无；无 | `modules/moisture/src/moisture/domain/errors.py` | `moisture/tests/integration/excel/test_source_parser.py` → `modules/moisture/tests/integration/excel/test_source_parser.py`、`modules/moisture/tests/contract/test_service_response_reader.py` | T06/T07/T14；不得把 traceback 写 stdout。 |
| `moisture/src/moisture/domain/formula_verification.py`：`verify_moisture` | 保留并适配 | `initial_mass,dry_mass,foil_mass,source_value,tolerance` → `FormulaVerification`；负 tolerance=`ValueError`；`Decimal`、domain models | `modules/moisture/src/moisture/domain/formula_verification.py` | `moisture/tests/unit/domain/test_formula_verification.py` → `modules/moisture/tests/unit/domain/test_formula_verification.py` | T07；算法和 Decimal 期望不顺便重写，口径仍待批准。 |
| `moisture/src/moisture/domain/models.py`：样本、部门、批次、统计、规则命中、复核模型 | 保留并适配 | typed fields → immutable Pydantic models；validation error；Pydantic、`Decimal/date/Path` | `modules/moisture/src/moisture/domain/models.py` | `moisture/tests/unit/domain/test_models.py` → `modules/moisture/tests/unit/domain/test_models.py` | T07；去旧合同 DTO/Path 身份，增加来源与 1—10 语义。 |
| `moisture/src/moisture/domain/review.py`：`apply_review` | 仅提取 | screening + 响应/降级原因 → review decision；无显式 raise；旧 `ports.llm` | `modules/moisture/src/moisture/domain/review.py`、`modules/moisture/src/moisture/application/review_state_applier.py` | `moisture/tests/unit/domain/test_review.py`、`moisture/tests/integration/ai/test_ai_review.py` → `modules/moisture/tests/unit/domain/test_review_state_applier.py`、`modules/moisture/tests/integration/test_finalize_service_responses.py` | T19；只留状态机/降级，改用正式 service response。 |
| `moisture/src/moisture/domain/rule_lifecycle.py`：状态转换、`RuleVersion`、`SimulationReport` | 仅提取 | 生命周期事件 → 验证/模拟记录；`RuleLifecycleError`；Pydantic、domain rules | `modules/moisture/src/moisture/domain/rules.py`（仅确认状态语义） | `moisture/tests/unit/rules/test_lifecycle.py` → `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；审批、职责分离和在线发布不迁。 |
| `moisture/src/moisture/domain/rules.py`：`RuleDefinition`、`RuleSetSnapshot`、`RuleContext` | 保留并适配 | definition/record/statistics → validated rule/context；`ValueError`；Pydantic、statistics | `modules/moisture/src/moisture/domain/rules.py` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_evaluators.py` | T10；增加精确 hash、来源、scope、客户确认状态。 |
| `moisture/src/moisture/domain/statistics.py`：`compute_batch_statistics` | 保留并适配 | `BatchRecord` → `BatchStatistics`；无可用值=`ValueError`；`Decimal`、stdlib statistics | `modules/moisture/src/moisture/domain/statistics.py` | `moisture/tests/unit/domain/test_statistics.py` → `modules/moisture/tests/unit/domain/test_statistics.py` | T07；保持旧数值回归，口径仍待批准。 |
| `moisture/src/moisture/infrastructure/config.py`：`JobConfig`、`ModuleSettings` | 不迁移 | 旧 JSON/config → 旧 DTO；`ValueError`/validation；Pydantic、Path | 无 | `moisture/tests/unit/test_config.py` → 无 | T20；正式 job schema 是唯一任务合同。 |
| `moisture/src/moisture/infrastructure/hashing.py`：`sha256_file` | 保留并适配 | 文件 Path → 十六进制 SHA-256；I/O 异常透传；`hashlib` | `modules/moisture/src/moisture/infrastructure/hashing.py` | `moisture/tests/integration/excel/test_source_parser.py` 的 hash 断言 → `modules/moisture/tests/unit/test_hashing.py`、`modules/moisture/tests/unit/test_file_integrity.py` | T08；流式 hash，用于内容身份，不混入绝对路径。 |
| `moisture/src/moisture/ports/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/ports/__init__.py` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_evaluators.py`（其余 port 由各消费者测试覆盖） | T09/T10/T11/T12；不导出旧 Provider/Job DTO。 |
| `moisture/src/moisture/ports/experience_repository.py`：metadata/query/reference/protocol | 保留并适配 | metadata/query → references；`ValueError`/validation；Pydantic、BatchRecord | `modules/moisture/src/moisture/ports/experience_repository.py` | `moisture/tests/unit/experience/test_scope_matcher.py`、`moisture/tests/integration/experience/test_local_markdown.py` → `modules/moisture/tests/unit/experience/test_scope_matcher.py`、`modules/moisture/tests/unit/experience/test_local_approved_repository.py` | T12；只读且只允许已审核结构化经验参与复判。 |
| `moisture/src/moisture/ports/llm.py`：旧 profile/request/response/errors/`LLMPort` | 仅提取 | Provider profile + request → Provider response/errors；多种 validation；Pydantic、URL、experience | `modules/moisture/src/moisture/domain/review.py`、`modules/moisture/schemas/ai-review-response.schema.json` | `moisture/tests/contract/llm/test_gateway.py`、`moisture/tests/integration/ai/test_ai_review.py` → `modules/moisture/tests/unit/test_ai_request_builder.py`、`modules/moisture/tests/unit/test_service_response_validator.py` | T17/T19；只提取候选、证据绑定和业务响应字段，`LLMPort`/profile/transport errors 不迁。 |
| `moisture/src/moisture/ports/rule_evaluator.py`：`RuleEvaluator` | 保留并适配 | record/context/definition → `RuleHit` 或 `None`；实现决定；domain rules/models | `modules/moisture/src/moisture/ports/rule_evaluator.py` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_evaluators.py` | T10；唯一窄规则扩展点。 |
| `moisture/src/moisture/ports/rule_repository.py`：可写 repository + simulator protocols | 仅提取 | save/publish/get/simulate → snapshots/reports；实现决定；Path、lifecycle | `modules/moisture/src/moisture/ports/rule_repository.py`（只读 loader port） | `moisture/tests/integration/rules/test_local_repository.py` → `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；删除 save/publish/active pointer 和运行时模拟 port。 |
| `moisture/src/moisture/ports/workbook_parser.py`：`WorkbookParserPort` | 保留并适配 | `Path,default_year` → `BatchRecord`；实现决定；Path/domain model | `modules/moisture/src/moisture/ports/workbook_parser.py` | `moisture/tests/integration/excel/test_source_parser.py` → `modules/moisture/tests/integration/excel/test_source_parser.py` | T09；不暴露旧 JobConfig/宿主 DTO。 |
| `moisture/src/moisture/ports/writers.py`：内部 outputs/result 及 writer protocols | 仅提取 | internal run data + Path → artifacts/result；`ValueError`/validation；Pydantic、domain models | `modules/moisture/src/moisture/application/run_result.py`、`modules/moisture/src/moisture/ports/writers.py` | `moisture/tests/integration/output/test_result_writer.py`、`moisture/tests/integration/output/test_summary_writer.py`、`moisture/tests/integration/output/test_markdown_writer.py` → `modules/moisture/tests/contract/test_result_mapper.py`、`modules/moisture/tests/integration/output/test_xlsx_writer.py`、`modules/moisture/tests/integration/output/test_markdown_writer.py` | T05/T11/T13；与官方 ModuleResult 隔离。 |

## 4. 运行文件逐项处置：Excel、规则、经验、报告、AI 与 CLI

| 旧运行文件（主要符号） | 处置 | 旧边界；异常；依赖 | 新目标 | 旧测试 → 未来测试 | Task / 适配 |
|---|---|---|---|---|---|
| `moisture/src/moisture/adapters/excel/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/adapters/excel/__init__.py` | `moisture/tests/integration/excel/test_source_parser.py` → `modules/moisture/tests/integration/excel/test_source_parser.py` | T09；不复制。 |
| `moisture/src/moisture/adapters/excel/source_parser.py`：`ExcelSourceParser` 及四类结构/完整性异常 | 保留并适配 | `.xlsx Path,default_year` → `BatchRecord`；结构歧义、样本超限、源文件改变；openpyxl、template detector、formula、hashing | `modules/moisture/src/moisture/adapters/excel/source_parser.py` | `moisture/tests/integration/excel/test_source_parser.py` → `modules/moisture/tests/integration/excel/test_source_parser.py` | T09；仅 job 输入，1—10，11 失败不截断，结构化 issue。 |
| `moisture/src/moisture/adapters/excel/summary_writer.py`：`write_summary_xlsx`、五 sheet writers | 保留并适配 | `RunResult,Path` → XLSX；writer/I/O 异常；XlsxWriter、old writer DTO | `modules/moisture/src/moisture/reporting/xlsx_writer.py` | `moisture/tests/integration/output/test_summary_writer.py` → `modules/moisture/tests/integration/output/test_xlsx_writer.py` | T11；output_dir 内原子写，颜色按正式 severity 语义。 |
| `moisture/src/moisture/adapters/excel/template_detector.py`：candidate/row scan/score | 保留并适配 | worksheet pairs → header/sample candidates；无显式 raise；openpyxl、Decimal | `modules/moisture/src/moisture/adapters/excel/template_detector.py` | `moisture/tests/integration/excel/test_source_parser.py` → `modules/moisture/tests/integration/excel/test_source_parser.py` | T09；动态识别，同分不得静默猜测。 |
| `moisture/src/moisture/adapters/rules/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/adapters/rules/__init__.py` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_evaluators.py` | T10；不复制。 |
| `moisture/src/moisture/adapters/rules/builtin_evaluators.py`：六类 evaluator、`screen` | 保留并适配 | record + snapshot → screening decisions/hits；非法字段/operator=`ValueError`；registry、domain rules/statistics | `modules/moisture/src/moisture/adapters/rules/builtin_evaluators.py` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_evaluators.py` | T10；只执行 confirmed 规则；旧阈值不代表批准。 |
| `moisture/src/moisture/adapters/rules/evaluator_registry.py`：`RuleTypeRegistry` | 保留并适配 | evaluator type → register/get；重复/未知=`ValueError`；rule evaluator port | `modules/moisture/src/moisture/adapters/rules/evaluator_registry.py` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_evaluators.py` | T10；只允许六类显式 evaluator。 |
| `moisture/src/moisture/adapters/rules/local_yaml_repository.py`：可写版本库、active pointer、audit | 仅提取 | YAML/repository operations → definitions/snapshots；validation/integrity/not-found；PyYAML、filesystem、lifecycle | `modules/moisture/src/moisture/adapters/rules/package_loader.py` | `moisture/tests/integration/rules/test_local_repository.py` → `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；只提取安全读取、Schema/hash，删除写入/发布/audit。 |
| `moisture/src/moisture/adapters/rules/simulator.py`：`RuleSimulator` | 仅测试 | paths + snapshot → `SimulationReport`；路径/hash=`ValueError`；parser、repository、screen | `modules/moisture/tests/helpers/rule_simulator.py` | `moisture/tests/integration/rules/test_local_repository.py` → `modules/moisture/tests/unit/rules/test_package_loader.py`（fixture simulation） | T10；不进入运行入口。 |
| `moisture/src/moisture/adapters/experience/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/adapters/experience/__init__.py` | `moisture/tests/unit/experience/test_scope_matcher.py` → `modules/moisture/tests/unit/experience/test_scope_matcher.py` | T12；不复制。 |
| `moisture/src/moisture/adapters/experience/local_markdown.py`：只读 repository、安全读取和治理校验 | 仅提取 | approved Markdown + query/id → references；validation/conflict/security；JSON Schema、PyYAML、filesystem | `modules/moisture/src/moisture/adapters/experience/local_approved_repository.py` | `moisture/tests/integration/experience/test_local_markdown.py` → `modules/moisture/tests/unit/experience/test_local_approved_repository.py` | T12；只读 approved，普通文本只引用。 |
| `moisture/src/moisture/adapters/experience/scope_matcher.py`：normalize/match | 保留并适配 | metadata + query → rank/match；无；Unicode、experience port | `modules/moisture/src/moisture/adapters/experience/scope_matcher.py` | `moisture/tests/unit/experience/test_scope_matcher.py` → `modules/moisture/tests/unit/experience/test_scope_matcher.py` | T12；确定性 scope 与稳定排序；供应商映射仍待批准。 |
| `moisture/src/moisture/adapters/reporting/__init__.py` | 按需重建 | package import → namespace；无；无 | `modules/moisture/src/moisture/reporting/__init__.py` | `moisture/tests/integration/output/test_markdown_writer.py` → `modules/moisture/tests/integration/output/test_markdown_writer.py` | T11/T13；路径按新分层重建。 |
| `moisture/src/moisture/adapters/reporting/markdown_writer.py`：`write_analysis_markdown` | 保留并适配 | `RunResult,Path` → Markdown；Jinja/I/O 异常；Jinja2、old atomic writer | `modules/moisture/src/moisture/reporting/markdown_writer.py` | `moisture/tests/integration/output/test_markdown_writer.py` → `modules/moisture/tests/integration/output/test_markdown_writer.py` | T13；StrictUndefined、规则 hash/来源/降级，删除越权结论。 |
| `moisture/src/moisture/adapters/reporting/result_writer.py`：Schema 验证与原子 JSON | 仅提取 | old `RunResult,Path` → old result JSON；Schema/I/O 异常；jsonschema、old DTO | `modules/moisture/src/moisture/contract/mapper.py`、`modules/moisture/src/moisture/infrastructure/atomic_write.py` | `moisture/tests/integration/output/test_result_writer.py` → `modules/moisture/tests/contract/test_atomic_result.py` | T05；只提取原子性，旧 payload/schema 不迁。 |
| `moisture/src/moisture/adapters/llm/__init__.py` | 不迁移 | package import → Provider namespace；无；无 | 无 | LLM tests → 仅业务部分重写 | T20；模块无 Provider 包。 |
| `moisture/src/moisture/adapters/llm/azure_openai.py`：`AzureOpenAIAdapter` | 不迁移 | profile/request → Azure HTTP；transport errors；旧 OpenAI adapter | 无 | `test_openai_compatible.py` Azure 合同 → 无 | T20；Provider/API Key/网络为宿主职责。 |
| `moisture/src/moisture/adapters/llm/gateway.py`：retry + response validation | 不迁移 | request/profile → retried Provider response；confidence/transport；time、`LLMPort`、response validator | 无（业务 validator 另见下一项） | `test_gateway.py` 业务绑定 → 新 request/response tests；retry/HTTP 不迁 | T17/T19/T20；不迁 gateway 或重试器。 |
| `moisture/src/moisture/adapters/llm/openai_compatible.py`：HTTPX adapter | 不迁移 | prompt/profile → HTTP completion；transport/timeout/response；HTTPX、Provider DTO、redaction | 无 | `moisture/tests/contract/llm/test_openai_compatible.py` → 无 | T20；HTTPX、厂商格式、网络重试全部禁止。 |
| `moisture/src/moisture/adapters/llm/prompt_builder.py`：`build_review_prompt` | 仅提取 | bounded request → normalized prompt；configuration error；JSON、Pydantic、old LLM DTO | `modules/moisture/src/moisture/application/ai_request_builder.py` | `moisture/tests/contract/llm/test_gateway.py` → `modules/moisture/tests/unit/test_ai_request_builder.py` | T17；只迁最小/预算断言，改为主框架 service request payload，不造 HTTP prompt。 |
| `moisture/src/moisture/adapters/llm/provider_factory.py`：`ProviderFactory` | 不迁移 | env/profile → Provider adapter；configuration/unavailable；OS env、厂商 adapters | 无 | `moisture/tests/contract/llm/test_provider_factory.py` → 无 | T20；禁止环境 API Key 和 Provider 选择。 |
| `moisture/src/moisture/adapters/llm/redaction.py`：日志/异常树脱敏 | 仅提取测试意图 | exceptions/log records + secrets → redacted copies；无；logging | `modules/moisture/src/moisture/application/ai_request_builder.py` 的字段 allowlist | `moisture/tests/contract/llm/test_openai_compatible.py` 的不泄密断言 → `modules/moisture/tests/unit/test_ai_request_builder.py` | T17；从源头最小化 payload，不迁全局日志 filter。 |
| `moisture/src/moisture/adapters/llm/response_validator.py`：`validate_review_response` | 仅提取 | request + business response → validated response；`LLMResponseError`；Decimal、domain colors | `modules/moisture/src/moisture/application/service_response_validator.py` | `moisture/tests/contract/llm/test_gateway.py`、`moisture/tests/integration/ai/test_ai_review.py` → `modules/moisture/tests/unit/test_service_response_validator.py` | T19；按正式 envelope 严格绑定 request/rule/candidate/direction/field/value。 |
| `moisture/src/moisture/application/ai_review.py`：request 构造、经验筛选、Provider 调用、audit、状态应用 | 仅提取 | screening/record/rule/experience → review decisions/audit；内部降级；gateway、UUID/time、Pydantic | `modules/moisture/src/moisture/application/ai_request_builder.py`、`modules/moisture/src/moisture/application/service_response_validator.py`、`modules/moisture/src/moisture/application/review_state_applier.py` | `moisture/tests/integration/ai/test_ai_review.py` → `modules/moisture/tests/unit/test_ai_request_builder.py`、`modules/moisture/tests/integration/test_finalize_service_responses.py` | T17/T19；只提取业务绑定/降级/状态，Provider call、进程内审计、随机 ID 不迁。 |
| `moisture/src/moisture/application/rule_management.py`：`RuleManagementService` | 不迁移 | draft/save/simulate/review/publish → active rule；lifecycle/职责分离/模拟异常；可写 repository | 无 | lifecycle/local repository 管理断言 → 无运行时管理测试 | T20；运行时规则发布禁止。 |
| `moisture/src/moisture/cli.py`：`main`、`entrypoint` | 仅提取（命令风格参考） | argv → identity text/exit；`SystemExit`；argparse、old constants | `modules/moisture/src/moisture/cli.py` | `moisture/tests/unit/test_cli.py` → `modules/moisture/tests/contract/test_cli_health.py`、`modules/moisture/tests/contract/test_run_contract.py` | T02/T03；只实现正式三命令，stdout 仅协议。 |

## 5. 模块包、配置、规则、Schema 与模板资产逐项处置

| 旧资产 | 处置 | 输入/输出与依赖 | 新目标 | 旧测试 → 未来测试 | Task / 适配 |
|---|---|---|---|---|---|
| `moisture/module.json` | 仅作参考并重建 | 旧 manifest → 旧能力声明 | `modules/moisture/module.json` | 旧：无 manifest 合同测试 → `modules/moisture/tests/contract/test_manifest.py` | T02；去 `incremental=true`、optional LLM/UI，严格按官方 Schema。 |
| `moisture/run_module.bat` | 仅作参考并重建 | argv → Python CLI exit；依赖 PATH Python | `modules/moisture/run_module.bat` | `moisture/tests/unit/test_cli.py` → `modules/moisture/tests/contract/test_cli_health.py`、`modules/moisture/tests/contract/test_run_contract.py` | T02/T03；设置模块 src、转发退出码、不硬编码机器路径。 |
| `moisture/pyproject.toml` | 仅作打包参考 | build/test metadata → package | `modules/moisture/pyproject.toml` | 旧：无直接测试 → `modules/moisture/tests/contract/test_cli_health.py`、T20 依赖扫描 | T02/T20；删除 HTTPX/FastAPI/Uvicorn/身份依赖。 |
| `moisture/requirements.txt` | 仅作依赖参考 | pip requirements → runtime env | `modules/moisture/requirements.txt` | 旧：无直接测试 → `modules/moisture/tests/contract/test_cli_health.py`、T20 依赖扫描 | T02/T20；只保留离线模块必要库。 |
| `moisture/config/llm.example.yaml` | 不迁移 | Provider URLs/models/env key names → 联网配置 | 无 | 无 | T20；Provider、API Key、HTTP 配置禁止。 |
| `moisture/experience/README.md` | 仅提取说明 | Markdown governance example → 人工说明 | `modules/moisture/experience/manifest.json`、`modules/moisture/README.md` | `moisture/tests/integration/experience/test_local_markdown.py` → `modules/moisture/tests/unit/experience/test_local_approved_repository.py`、T23 文档检查 | T12/T23；不复制示例身份/路径，结构化经验仍需批准。 |
| `moisture/rules/default_rules.yaml` | 仅作业务参考 | 0.55/0.47 old published rules → screening definitions | `modules/moisture/rules/active/rules.yaml`、`modules/moisture/rules/active/rule-package.json` | `moisture/tests/unit/rules/test_evaluators.py`、`moisture/tests/integration/rules/test_local_repository.py` → `modules/moisture/tests/unit/rules/test_package_loader.py`、`modules/moisture/tests/fixtures/rule_packages/` | T10；阈值必须 pending，旧 published 非批准证据。 |
| `moisture/schemas/experience.schema.json` | 仅提取（业务语义来源） | experience metadata JSON → validation | `modules/moisture/schemas/experience.schema.json` | `moisture/tests/integration/experience/test_local_markdown.py` → `modules/moisture/tests/unit/experience/test_local_approved_repository.py` | T12；按新 approved repository 重建。 |
| `moisture/schemas/job.schema.json` | 不迁移 | old job JSON → old DTO | 无；改用官方 Schema 精确副本 | schema-lock tests | T04；禁止第二套 Job 合同。 |
| `moisture/schemas/llm_review.schema.json` | 仅提取（业务语义来源） | old LLM text JSON → old response | `modules/moisture/schemas/ai-review-response.schema.json` | `moisture/tests/contract/llm/test_gateway.py` → `modules/moisture/tests/unit/test_service_response_validator.py` | T19；按正式计划的业务 JSON 约束重建，不作为主框架合同。 |
| `moisture/schemas/result.schema.json` | 不迁移 | old result payload → validation | 无；改用官方 Schema 精确副本 | schema-lock/mapper tests | T04/T05；旧形状禁止。 |
| `moisture/schemas/rule.schema.json` | 仅提取（业务语义来源） | rule definition → validation | `modules/moisture/schemas/rule-package.schema.json` | `moisture/tests/unit/rules/test_evaluators.py` → `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；只读 package + 客户确认状态。 |
| `moisture/schemas/rule_set.schema.json` | 仅提取（业务语义来源） | version/definitions/hash → validation | `modules/moisture/schemas/rule-package.schema.json` | `moisture/tests/integration/rules/test_local_repository.py` → `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；不保留可写 lifecycle。 |
| `moisture/templates/analysis_report.md.j2` | 保留并适配 | internal result → Markdown | `modules/moisture/templates/analysis_report.md.j2` | `moisture/tests/integration/output/test_markdown_writer.py` → `modules/moisture/tests/integration/output/test_markdown_writer.py` | T13；StrictUndefined；去旧责任/Provider 文案，增加规则 hash/来源/降级。 |

## 6. 旧测试、fixture 与 conftest 逐项路由

| 旧测试文件 | 处置与可保留断言 | 未来目标 | Task / 明确不迁内容 |
|---|---|---|---|
| `moisture/tests/__init__.py` | 按需重建测试包，不复制 | `modules/moisture/tests/__init__.py` | T02；无业务断言。 |
| `moisture/tests/fixtures/__init__.py` | 按需重建 fixture 包，不复制 | `modules/moisture/tests/fixtures/__init__.py` | T09；无业务断言。 |
| `moisture/tests/fixtures/workbook_factory.py` | 仅测试；保留合成 workbook、公式缓存/格式操控能力 | `modules/moisture/tests/fixtures/workbook_factory.py` | T09/T11；不得包含客户原始表。 |
| `moisture/tests/contract/llm/conftest.py` | 仅提取 bounded candidate/experience fixture | `modules/moisture/tests/fixtures/service_requests.py` | T17/T19；去 Provider profile。 |
| `moisture/tests/contract/llm/test_gateway.py` | 仅提取最小 payload、预算、规则/证据/方向/字段/数值绑定、禁止责任结论 | `modules/moisture/tests/unit/test_ai_request_builder.py`、`test_service_response_validator.py` | T17/T19；gateway retry、HTTP 4xx/5xx、Provider confidence 配置不迁。 |
| `moisture/tests/contract/llm/test_openai_compatible.py` | 不迁移 | 无 | T20；HTTPX、Azure/OpenAI 格式、API Key、Retry-After、日志 filter 整组禁止。 |
| `moisture/tests/contract/llm/test_provider_factory.py` | 不迁移 | 无 | T20；Provider factory/env API Key 整组禁止。 |
| `moisture/tests/integration/ai/test_ai_review.py` | 仅提取 deterministic request、隔离降级、精确证据绑定、橙绿→红蓝业务状态 | `modules/moisture/tests/integration/test_finalize_service_responses.py`、unit request tests | T17/T19；每候选 Provider call、UUID/time audit、进程内 gateway 不迁。 |
| `moisture/tests/integration/excel/test_source_parser.py` | 保留并适配 1/2/6/10、11 失败、sheet/header、公式、metadata、hash、源文件不变 | `modules/moisture/tests/integration/excel/test_source_parser.py` | T08/T09；去旧路径/JobConfig。 |
| `moisture/tests/integration/experience/test_local_markdown.py` | 仅提取 published/approved、Schema、scope、冲突、path/symlink、安全读取、排序 | `modules/moisture/tests/unit/experience/test_local_approved_repository.py` | T12；在线写入/用户治理不增加。 |
| `moisture/tests/integration/output/conftest.py` | 仅测试；按新内部模型重建 run result fixture | `modules/moisture/tests/fixtures/run_results.py` | T05/T11/T13；旧 Result DTO 不迁。 |
| `moisture/tests/integration/output/test_markdown_writer.py` | 保留并适配章节、引用、降级和空经验 | `modules/moisture/tests/integration/output/test_markdown_writer.py` | T13；去旧责任/Provider 文案。 |
| `moisture/tests/integration/output/test_result_writer.py` | 仅提取原子替换、temp 清理、计数一致性和 Schema-before-write 意图 | `modules/moisture/tests/contract/test_atomic_result.py`、`test_result_mapper.py` | T05；旧 result schema/字段断言不迁。 |
| `moisture/tests/integration/output/test_summary_writer.py` | 保留并适配五表、图表、确定性、公式注入防护、颜色/格式、temp 清理 | `modules/moisture/tests/integration/output/test_xlsx_writer.py` | T11；颜色 severity 按正式计划。 |
| `moisture/tests/integration/rules/test_local_repository.py` | 仅提取 read/Schema/hash、安全路径、生产 parser 联动 | `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；publish、active pointer、audit、simulation lifecycle 不进 runtime。 |
| `moisture/tests/unit/domain/test_formula_verification.py` | 保留并适配全部 Decimal 公式边界 | `modules/moisture/tests/unit/domain/test_formula_verification.py` | T07；旧期望是迁移基线，不是业务批准。 |
| `moisture/tests/unit/domain/test_models.py` | 保留并适配 1—10、0/11 拒绝、不可变标识 | `modules/moisture/tests/unit/domain/test_models.py` | T07；去旧 Pydantic 合同耦合。 |
| `moisture/tests/unit/domain/test_review.py` | 仅提取状态机、降级保色、方向矛盾、红蓝仍待人工 | `modules/moisture/tests/unit/domain/test_review_state_applier.py` | T19；旧 `LLMReviewResponse` 改正式 service response。 |
| `moisture/tests/unit/domain/test_statistics.py` | 保留并适配均值/标准差/四分位/IQR/部门差/单样本/高精度 | `modules/moisture/tests/unit/domain/test_statistics.py` | T07；旧 legacy constructor 兼容断言不迁；口径仍待批准。 |
| `moisture/tests/unit/experience/test_scope_matcher.py` | 保留并适配 NFKC/空白/case、wildcard、排序和季节 | `modules/moisture/tests/unit/experience/test_scope_matcher.py` | T12；供应商/部门映射仍待批准。 |
| `moisture/tests/unit/rules/test_evaluators.py` | 保留并适配六类 evaluator、registry、Schema、scope、颜色方向 | `modules/moisture/tests/unit/rules/test_evaluators.py` | T10；未批准阈值只能 fixture/pending。 |
| `moisture/tests/unit/rules/test_lifecycle.py` | 仅提取治理 metadata、immutable package、路径 token 和 pending/confirmed 语义 | `modules/moisture/tests/unit/rules/test_package_loader.py` | T10；作者审批/职责分离/在线 transition 不迁。 |
| `moisture/tests/unit/test_cli.py` | 仅提取 machine-readable version 意图 | `modules/moisture/tests/contract/test_cli_health.py` | T02；旧 identity 文本/参数不迁。 |
| `moisture/tests/unit/test_config.py` | 不迁移 | 无 | T20；旧 JobConfig 整组禁止。 |

## 7. 全树其余资产的边界

- 21 份 `2026年4月份/*.xlsx`：**不迁移**。它们是客户原始业务数据；未来仅可人工批准后据其结构创建脱敏合成 fixture，不能复制文件或内容。
- `.gitignore`、`docs/superpowers/**`、`品质Agent模块交接说明.md`、`竹丝水分检测模块新方案_V0.2.md` 和两张微信图片：**不作为运行资产迁移**。仅用于历史取证，正式计划/批准架构/机器合同优先。
- 稳定提交没有 FastAPI Web 路由、Identity、Session、Cookie 或 CSRF 运行文件；这些属于后续旧 Task 10 能力，仍明确禁止。

## 8. 禁止资产清单

下列能力不得以重命名、兼容层、可选依赖、fixture 帮助器或“未来接口”进入正式运行时：

- `web`、FastAPI、Uvicorn、Web templates、GUI。
- `identity`、LocalIdentityRepository、用户、密码、角色、`session`、Cookie、`csrf`。
- `rules-ui`、`rules-user`、可写 repository、runtime rule publish、在线审批。
- `provider`、OpenAI compatible、Azure OpenAI、HTTPX gateway、retry、API Key、Windows credentials、Provider factory/profile。
- 框架 SQLite、隐藏数据库、draft 进程内存延续。
- 旧 `JobConfig`、`job.schema.json`、`result.schema.json` 和旧 manifest 能力声明。
- 客户原始工作簿、个人绝对路径、密钥、`.env`、cache 和后续旧 Task 10 代码。

## 9. 完整性结论与后续门槛

- 84/84 个 Task 1—9 运行/测试/fixture/package 资产均有逐文件处置；46/46 个运行文件记录了符号或职责、输入/输出、异常、依赖、目标、测试和 Task。
- 所有可迁条目均是“先旧测试意图、后未来失败测试、再最小实现”的路由；没有“复制整个目录”或整体 cherry-pick。
- Provider/HTTP/身份/运行时发布明确不迁；LLM 只提取与正式 service request/response 相容的业务校验语义。
- 后续若发现未列入本清单的旧运行文件或测试，默认禁止迁移；必须先补充目标、未来失败测试、处置理由和业务批准状态，再进入对应 Task。
