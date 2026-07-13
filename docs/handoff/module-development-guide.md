# 竹简工作台模块开发与交付指南

本指南适用于三个业务模块负责人。框架只接收独立、可验证的模块包，不接收需要修改框架代码才能运行的零散脚本。

## 1. 身份、分支与目录

| 业务 | `module_id` | 分支 | 仓库目录 | 交付压缩包 |
|---|---|---|---|---|
| 竹丝水分 | `moisture` | `module/moisture` | `modules/moisture/` | `moisture-<version>.zip` |
| 水煮实验 | `boiling` | `module/boiling` | `modules/boiling/` | `boiling-<version>.zip` |
| 售后分析 | `after_sales` | `module/after-sales` | `modules/after_sales/` | `after_sales-<version>.zip` |

收到私有仓库邀请后，克隆仓库并切换到指定分支。以水分模块为例：

```powershell
git clone <PRIVATE_REPOSITORY_URL>
cd BambooWorkbench
git switch module/moisture
Copy-Item -Recurse mock_modules/moisture modules/moisture
```

模拟包 `mock_modules/moisture`、`mock_modules/boiling`、`mock_modules/after_sales` 是接口样板，不包含业务算法。只替换自己模块目录内的实现。

## 2. 允许和禁止的访问边界

模块可以读取任务 JSON 中明确列出的输入副本、自己的配置和规则；只能向任务指定的 `output_dir` 写成果。

模块不得：

- 修改 `app/`、`core/`、`ui/`、`contracts/`、`.github/`；
- 直接连接框架 SQLite、读取 Windows 凭据或 API 密钥；
- 读取其他模块目录、扫描用户磁盘或修改原始 Excel；
- 绕过 `service_requests` 自行调用框架 AI 或知识库；
- 硬编码开发者电脑路径、客户姓名、账号或密钥；
- 用弹窗或独立 GUI 代替命令行协议。

## 3. 模块包最低结构

```text
modules/<module_id>/
├─ module.json
├─ run_module.bat
├─ README.md
├─ CHANGELOG.md
├─ requirements.txt
├─ src/
├─ rules/
├─ templates/
├─ tests/
├─ samples/
│  ├─ input/
│  └─ expected/
└─ docs/
   ├─ 字段映射表.md
   ├─ 计算公式与判定规则.md
   ├─ 人工确认边界.md
   └─ 已知限制.md
```

其中 `src/`、`tests/`、`samples/` 和 `docs/` 是合同验证的必需目录。模板、规则和依赖必须包含在模块包内。

## 4. `module.json` 全部字段

结构以 [`contracts/schemas/module-manifest.schema.json`](../../contracts/schemas/module-manifest.schema.json) 为唯一机器合同。

| 字段 | 要求 |
|---|---|
| `schema_version` | 固定为 `1.0` |
| `module_id` | 只能是 `moisture`、`boiling`、`after_sales` 中本人负责的一项 |
| `module_name` | 中文展示名，1–80 字符 |
| `module_version` | 三段式版本，如 `0.1.0` |
| `entrypoint` | 模块内相对路径，只允许 `.bat` 或 `.cmd` |
| `supported_extensions` | 至少一种带点扩展名，如 `[".xlsx"]` |
| `supports_single_file` | 是否支持单文件 |
| `supports_batch` | 是否支持批量 |
| `supports_incremental` | 是否支持增量处理 |
| `requires_network` | 是否必须联网；能离线时应为 `false` |

不要添加未定义字段。健康检查由框架调用入口脚本的 `self-check` 命令，不在 `module.json` 增加自定义命令字段。

## 5. 三条强制命令

```powershell
modules\<module_id>\run_module.bat version
modules\<module_id>\run_module.bat self-check
modules\<module_id>\run_module.bat run --job D:\absolute\path\job.json
```

退出码：`0` 表示协议结果已生成；`2` 表示任务输入不合法；`3` 表示运行失败；`4` 表示依赖或运行环境缺失。标准输出只能逐行输出 JSON 进度；诊断文字写标准错误。

```json
{"type":"progress","percent":40,"message":"正在处理第 4 个文件"}
```

## 6. 任务输入与两阶段流程

可执行样例见 [`contracts/examples/job.json`](../../contracts/examples/job.json)，结构定义由 `core/contracts/job.py` 导出。关键字段包括：

- `phase`：`draft` 或 `finalize`；
- `run_mode`：`single` 或 `batch`；
- `input_files`：框架创建的只读输入副本绝对路径；
- `output_dir`：本阶段唯一允许写入的目录；
- `allowed_knowledge_scopes`：本模块可请求的知识域；
- `confirmation_file`、`service_response_file`：只在正式阶段提供。

标准顺序：

```text
phase=draft
→ 模块生成草稿 result.json
→ 框架展示模块确认项和 AI 脱敏授权
→ 框架解析知识/AI service_requests
→ 框架写 confirmation.json 与 service-response.json
→ phase=finalize 重新调用同一模块
→ 模块读取确认和服务响应并生成正式 result.json
```

`phase=finalize` 时必须使用 `parent_job_id`、`confirmation_file`；存在公共服务请求时框架同时传入 `service_response_file`。模块不得猜测文件位置。

确认文件示例：

```json
{
  "schema_version": "1.0",
  "job_id": "20260713-0001",
  "answers": [
    {"confirmation_id":"C-001","value":"人工确认值","apply_to_batch":false,"remember_mapping":false}
  ]
}
```

服务响应示例：

```json
{
  "schema_version": "1.0",
  "task_id": "20260713-0001",
  "module_id": "moisture",
  "responses": [
    {"request_id":"kb-1","service":"knowledge","status":"ok","items":[]},
    {"request_id":"ai-1","service":"ai","status":"denied","text":null}
  ]
}
```

AI 被拒绝是正常业务状态，模块必须继续生成不依赖 AI 的本地结果。

## 7. `result.json` 要求

参考 [`contracts/examples/result.json`](../../contracts/examples/result.json) 和导出 Schema。每次运行必须生成结构合法的 `result.json`，任务、模块和输入来源必须与 `job.json` 一致。

必须正确填写：

- `status`、`summary`、`file_results`、`errors`；
- 每个异常的等级、规则编号、说明、建议和 `source`；
- 每个人工确认项的原因、候选值、置信度、阻塞性和来源；
- 每个输出文件的绝对路径、类型、标签和 MIME 类型；
- `rule_version`、`analysis_summary`、开始和结束时间；
- 可选 `service_requests`。

服务请求只能出现在草稿阶段。知识请求必须指定允许的 `scope` 和非空 `payload.query`；AI 请求必须说明 `purpose`，默认 `requires_user_consent: true`。

## 8. 必须提交的测试

每个模块至少覆盖：

1. 正常单文件和批量成功；
2. 部分文件失败仍返回 `partial_success`；
3. 关键字段缺失或规则冲突进入人工确认；
4. 非法任务 JSON、错误扩展名和恶意路径被拒绝；
5. 超时和取消后子进程退出且不留下半成品；
6. 损坏 Excel、空文件和格式变化不会导致无结构崩溃；
7. `phase=finalize` 正确使用确认与服务响应；
8. 原始文件哈希在运行前后保持一致；
9. 同一输入重复运行不会错误重复统计；
10. 所有业务样本都有脱敏输入与可机读预期结果。

业务核心字段、公式和判定样本必须 100% 符合负责人提供的预期结果。框架测试只验证协议，不能替负责人证明业务计算正确。

## 9. 提交前命令

在仓库根目录运行对应命令：

```powershell
python -m app.tools.module_contract_cli validate modules/moisture
python -m app.tools.module_contract_cli validate modules/boiling
python -m app.tools.module_contract_cli validate modules/after_sales
python -m pytest modules/<module_id>/tests -q
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

只运行本人模块对应的第一条合同命令。提交时附上命令输出、测试日志、输入与预期结果对应表，以及成功/异常/人工确认三个界面截图。

## 10. 数据脱敏与交付清单

- 使用虚构客户、订单、电话、地址和人员；
- 移除 Excel 元数据、隐藏表、批注、外链和历史作者；
- 不交付真实企业原表、运行日志、SQLite、`.env`、密钥或 API 响应；
- 每个样本写明其覆盖场景，但不得通过文件名泄露客户信息；
- ZIP 之外另附 SHA-256 校验值。

正式交付包括模块 ZIP、源代码、规则与模板、依赖清单、自动测试、脱敏样本、预期结果、示例输出、字段/公式/规则/人工边界文档、测试日志和已知限制。

## 11. 提交与评审

提交只进入本人 `module/*` 分支，Pull Request 目标必须是 `integration`，不得直接合并到 `main`。PR 通过 `quality`、合同验证和 [`module-acceptance-checklist.md`](module-acceptance-checklist.md) 后，才可进入后续框架接入。客户尚未验收的规则必须标记为“待客户确认”，不得写成正式标准。
