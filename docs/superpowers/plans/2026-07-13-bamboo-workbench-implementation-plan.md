# BambooWorkbench（竹简工作台）实施计划

日期：2026-07-13  
项目根目录：`D:\Project\BambooWorkbench`  
目标：完成可运行、可演示、可接入三个独立业务模块的Windows本地桌面空框架。

## 1. 实施原则

1. 先固定协议和模拟模块，再开发页面，防止界面与模块接口脱节。
2. 框架只实现公共能力，不实现水分、水煮和售后的业务算法。
3. 每个阶段必须有自动测试和可见验收结果，通过后再进入下一阶段。
4. 所有代码、文档和测试只写入`D:\Project\BambooWorkbench`。
5. 真实企业Excel、客户资料、日志、密钥、数据库和生成结果不得提交GitHub。
6. `main`保持稳定；框架开发在`integration`；三个业务模块在各自`module/*`分支。
7. 第一版只验收Windows 10/11，核心代码避免不必要的Windows专属依赖。
8. 第一版发布时三个真实模块与主程序整体打包，不开发客户自行安装插件的界面。

## 2. 技术基线

- Python：3.12；
- 桌面界面：PySide6；
- 数据模型与协议校验：Pydantic 2；
- 数据库：Python标准库`sqlite3`；
- 本地目录：`platformdirs`；
- API访问：httpx；
- Windows安全凭据：keyring；
- YAML规则和配置：PyYAML；
- 测试：pytest、pytest-qt、pytest-cov；
- 代码质量：ruff；
- 打包：PyInstaller；
- Windows安装程序：Inno Setup；
- GitHub自动检查：GitHub Actions Windows Runner。

依赖统一写入`pyproject.toml`，开发依赖和运行依赖分组。项目使用仓库内`.venv`，该目录被Git忽略。

## 3. 目标仓库结构

```text
BambooWorkbench/
├─ .github/
│  ├─ workflows/
│  ├─ pull_request_template.md
│  └─ CODEOWNERS
├─ app/
│  ├─ __init__.py
│  ├─ __main__.py
│  ├─ bootstrap.py
│  └─ application.py
├─ core/
│  ├─ contracts/
│  ├─ modules/
│  ├─ tasks/
│  ├─ confirmations/
│  ├─ storage/
│  ├─ ai/
│  ├─ knowledge/
│  ├─ security/
│  └─ platform/
├─ ui/
│  ├─ main_window.py
│  ├─ navigation.py
│  ├─ pages/
│  ├─ widgets/
│  ├─ models/
│  └─ styles/
├─ modules/
│  ├─ moisture/
│  ├─ boiling/
│  └─ after_sales/
├─ mock_modules/
│  ├─ common/
│  ├─ moisture/
│  ├─ boiling/
│  └─ after_sales/
├─ contracts/
│  ├─ schemas/
│  └─ examples/
├─ resources/
│  ├─ icons/
│  ├─ logo/
│  ├─ fonts/
│  └─ themes/
├─ tests/
│  ├─ unit/
│  ├─ contract/
│  ├─ integration/
│  ├─ ui/
│  └─ packaging/
├─ packaging/
│  ├─ pyinstaller/
│  ├─ inno/
│  └─ scripts/
├─ docs/
│  ├─ superpowers/
│  ├─ framework/
│  ├─ modules/
│  ├─ testing/
│  └─ handoff/
├─ pyproject.toml
├─ README.md
├─ CHANGELOG.md
└─ .gitignore
```

## 4. 阶段0：仓库与开发环境

### 任务0.1：完善项目元数据

创建或修改：

- `pyproject.toml`；
- `README.md`；
- `CHANGELOG.md`；
- `.python-version`；
- `.gitignore`；
- `resources/logo/`中的正式矢量Logo资源；
- `resources/themes/bamboo.qss`的基础色彩令牌。

验收：

- 项目名称统一为`BambooWorkbench`；
- 中文界面名称统一为“竹简工作台”；
- 企业名称和团队名称统一；
- `python -m app`作为未来统一启动方式；
- `ruff`和`pytest`命令在虚拟环境可执行。

### 任务0.2：创建干净虚拟环境

步骤：

1. 使用Python 3.12创建`.venv`；
2. 安装运行和开发依赖；
3. 生成锁定依赖文件；
4. 执行最小导入测试；
5. 记录Windows环境安装方法。

验收：新终端按README命令可以完成安装，无需修改绝对路径。

### 任务0.3：创建GitHub私有仓库

步骤：

1. 在用户个人GitHub账号创建私有仓库`BambooWorkbench`；
2. 关联当前本地Git仓库；
3. 推送`main`；
4. 创建`integration`；
5. 配置`main`禁止直接推送；
6. 配置Pull Request模板和基础检查；
7. 在获得三名成员GitHub用户名后邀请协作者；
8. 协议冻结后从`integration`创建三个`module/*`分支。

验收：远程仓库私有，`main`和`integration`存在，未上传敏感文件。

## 5. 阶段1：公共协议与模块SDK

### 任务1.1：定义Pydantic协议模型

创建：

- `core/contracts/manifest.py`；
- `core/contracts/job.py`；
- `core/contracts/progress.py`；
- `core/contracts/result.py`；
- `core/contracts/confirmation.py`；
- `core/contracts/service_request.py`；
- `core/contracts/enums.py`。

模型覆盖：

- `module.json`；
- 草稿和finalize任务；
- 进度JSONL事件；
- 任务状态；
- 文件结果；
- 异常；
- 待确认；
- 成果文件；
- 来源追溯；
- AI/知识服务请求和响应；
- 结构化错误。

验收：所有示例JSON能够解析和重新序列化，非法状态、缺字段和错误类型会被拒绝。

### 任务1.2：导出JSON Schema和示例

创建：

- `contracts/schemas/*.schema.json`；
- `contracts/examples/job-draft.json`；
- `contracts/examples/job-finalize.json`；
- `contracts/examples/result-success.json`；
- `contracts/examples/result-confirmation.json`；
- `contracts/examples/progress.jsonl`；
- `contracts/examples/service-requests.json`。

验收：示例全部通过Schema校验；中文内容使用UTF-8。

### 任务1.3：实现模块合同测试CLI

创建：

- `core/contracts/validator.py`；
- `app/tools/module_contract_cli.py`；
- `tests/contract/`。

命令目标：

```text
python -m app.tools.module_contract_cli validate <模块目录>
```

检查：目录、清单、三条命令、协议输出、进度事件、敏感文件、绝对路径和原文件完整性。

验收：故意损坏的示例模块会得到明确失败原因，合法模拟模块通过。

## 6. 阶段2：模拟模块

### 任务2.1：实现模拟模块公共运行器

创建：

- `mock_modules/common/runner.py`；
- `mock_modules/common/scenarios.py`；
- `mock_modules/common/output_builder.py`。

模拟模块读取文件名或演示选项选择场景，不解析真实业务Excel。

### 任务2.2：实现三个模拟模块包

每个模拟模块包含真实交接包所需的：

- `module.json`；
- `run_module.bat`；
- `README.md`；
- `src/`；
- `tests/`；
- `samples/`。

支持场景：成功、部分成功、异常、待确认、finalize成功、超时、崩溃、错误JSON、缺少输出、AI请求和知识请求。

验收：三个模拟模块通过同一合同测试，没有框架特殊分支。

## 7. 阶段3：框架基础设施

### 任务3.1：应用路径和配置

创建：

- `core/platform/paths.py`；
- `core/platform/runtime.py`；
- `core/storage/settings.py`；
- `core/storage/file_store.py`。

统一处理开发环境、便携版、安装版和未来macOS路径。默认运行目录为`%LOCALAPPDATA%\BambooWorkbench`。

### 任务3.2：SQLite数据库

创建：

- `core/storage/database.py`；
- `core/storage/schema.py`；
- `core/storage/migrations.py`；
- `core/storage/repositories/`。

表：任务、任务文件、模块、进度摘要、异常、待确认、确认答案、成果文件、知识元数据、API授权记录和应用设置。

验收：首次启动自动建库；重复启动不重复建表；损坏数据库得到可读错误并保留备份。

### 任务3.3：结构化日志

创建：

- `core/platform/logging.py`；
- `core/platform/diagnostics.py`。

日志包含应用、任务和模块上下文；屏蔽密钥和敏感请求正文；支持从界面打开日志目录。

## 8. 阶段4：模块注册与独立进程运行

### 任务4.1：模块注册器

创建：

- `core/modules/registry.py`；
- `core/modules/manifest_loader.py`；
- `core/modules/healthcheck.py`。

能力：扫描模块目录、加载清单、检查版本、识别缺失、运行self-check、切换真实/模拟模块。

### 任务4.2：QProcess模块运行器

创建：

- `core/modules/process_runner.py`；
- `core/modules/progress_parser.py`；
- `core/modules/cancellation.py`；
- `core/modules/timeouts.py`。

能力：启动进程、逐行解析JSONL、捕获stderr、超时、取消、宽限终止、强制结束和退出码映射。

### 任务4.3：结果校验和文件核对

创建：

- `core/modules/result_loader.py`；
- `core/modules/output_verifier.py`；
- `core/modules/error_mapper.py`。

验收：模块崩溃、错误JSON、缺文件、非法路径和部分成功均转成框架可展示状态，主进程不退出。

## 9. 阶段5：任务状态机与两阶段确认

### 任务5.1：任务状态机

创建：

- `core/tasks/state_machine.py`；
- `core/tasks/service.py`；
- `core/tasks/job_builder.py`；
- `core/tasks/history.py`。

状态至少包含：新建、排队、运行、待确认、finalize运行、成功、部分成功、失败和取消。

### 任务5.2：任务输入快照和去重

创建：

- `core/tasks/fingerprints.py`；
- `core/tasks/input_snapshot.py`；
- `core/tasks/deduplication.py`。

框架复制本地任务输入副本并计算哈希，不修改原始文件。重复文件在创建任务前提示用户。

### 任务5.3：确认服务

创建：

- `core/confirmations/service.py`；
- `core/confirmations/serializer.py`；
- `core/confirmations/validation.py`。

能力：保存原建议、用户选择、确认时间、批量应用和阻塞状态；生成`confirmation.json`并重新调用原模块。

验收：未完成阻塞性确认不能进入正式成功；确认历史不可被后续结果覆盖。

## 10. 阶段6：PySide6前端

### 任务6.1：应用壳和主题

创建：

- `app/__main__.py`；
- `app/bootstrap.py`；
- `ui/main_window.py`；
- `ui/navigation.py`；
- `ui/styles/theme.py`；
- `resources/themes/bamboo.qss`；
- Logo和应用图标。

实现已确认的米白、深竹绿、浅绿、标题蓝和暖金视觉基线。

### 任务6.2：工作台

创建：

- `ui/pages/workbench_page.py`；
- `ui/widgets/module_card.py`；
- `ui/widgets/recent_tasks.py`。

展示企业名称、三个模块、真实/模拟状态、近期任务和待确认数量。

### 任务6.3：模块任务页

创建：

- `ui/pages/module_task_page.py`；
- `ui/widgets/file_drop_zone.py`；
- `ui/widgets/input_file_list.py`；
- `ui/models/input_files_model.py`。

支持拖拽、多文件、文件夹扫描、移除、重复提示和创建任务。

### 任务6.4：执行页

创建：

- `ui/pages/task_progress_page.py`；
- `ui/widgets/progress_summary.py`；
- `ui/widgets/file_progress_list.py`；
- `ui/widgets/log_summary.py`。

### 任务6.5：待确认中心

创建：

- `ui/pages/confirmations_page.py`；
- `ui/widgets/confirmation_card.py`；
- `ui/models/confirmations_model.py`。

支持单选、多选、文本、接受建议、批量应用、提交和阻塞提示。

### 任务6.6：结果中心

创建：

- `ui/pages/result_center_page.py`；
- `ui/widgets/result_metrics.py`；
- `ui/widgets/anomaly_list.py`；
- `ui/widgets/chart_preview.py`；
- `ui/widgets/output_files.py`。

### 任务6.7：历史、知识库和设置

创建：

- `ui/pages/history_page.py`；
- `ui/pages/knowledge_page.py`；
- `ui/pages/settings_page.py`；
- 对应表格模型和对话框。

验收：三个模拟模块从工作台到正式结果均可操作；键盘焦点、中文文本、窗口缩放和错误提示可用。

## 11. 阶段7：统一AI服务与知识库接口

### 任务7.1：AI设置与安全凭据

创建：

- `core/ai/settings.py`；
- `core/security/credentials.py`；
- `core/security/redaction.py`；
- `core/security/consent.py`。

API密钥通过keyring保存。测试使用模拟凭据后端，不连接真实API。

### 任务7.2：AI网关

创建：

- `core/ai/gateway.py`；
- `core/ai/providers/base.py`；
- `core/ai/providers/openai_compatible.py`；
- `core/ai/providers/mock.py`。

空框架默认使用mock provider。真实API调用只有在设置完整且用户确认脱敏预览后执行。

### 任务7.3：知识库元数据和模拟检索

创建：

- `core/knowledge/service.py`；
- `core/knowledge/namespaces.py`；
- `core/knowledge/importer.py`；
- `core/knowledge/providers/base.py`；
- `core/knowledge/providers/mock.py`。

实现公共与三个模块命名空间、文件元数据、启停、来源和模拟检索。生产级向量索引不在空框架验收范围。

### 任务7.4：公共服务请求闭环

模块返回`service_requests`后，框架完成知识查询、脱敏、授权、模拟或真实API调用，将结果写入`service_response_file`并进入finalize阶段。

验收：拒绝联网、未配置密钥、知识无结果和模拟成功均有完整状态与审计记录。

## 12. 阶段8：自动测试与质量门槛

### 任务8.1：单元测试

覆盖协议、状态机、路径、数据库、去重、确认、脱敏、知识命名空间和错误映射。

### 任务8.2：集成测试

覆盖模块注册、QProcess、三个模拟模块、超时、崩溃、取消、部分成功、AI请求和finalize。

### 任务8.3：UI测试

使用pytest-qt覆盖：启动、导航、文件添加、任务运行、待确认、结果、历史、设置和错误对话框。

### 任务8.4：端到端烟雾测试

建立一条命令在临时本地目录运行完整模拟流程，不依赖真实客户数据和网络。

### 任务8.5：CI

Windows GitHub Actions执行：

- 安装依赖；
- ruff；
- pytest；
- 合同测试；
- 敏感信息扫描；
- 最小PyInstaller构建检查。

质量门槛：严重缺陷为零；合同测试全部通过；核心状态机和模块运行器达到高覆盖；主分支不得合并失败检查。

## 13. 阶段9：打包

### 任务9.1：PyInstaller便携版

创建：

- `packaging/pyinstaller/BambooWorkbench.spec`；
- `packaging/scripts/build_portable.ps1`；
- `tests/packaging/test_portable_launch.py`。

验收：在未安装Python的干净Windows环境启动，进入工作台并完成模拟任务。

### 任务9.2：Inno Setup安装版

创建：

- `packaging/inno/BambooWorkbench.iss`；
- `packaging/scripts/build_installer.ps1`；
- 安装、升级和卸载检查清单。

验收：创建快捷方式；升级保留本地数据；卸载默认不删除用户任务和知识库。

## 14. 阶段10：交接、演示与发布

### 任务10.1：按真实代码重写模块交接说明

交付：

- `docs/handoff/module-development-guide.md`；
- `docs/handoff/module-package-checklist.md`；
- `docs/handoff/github-workflow.md`；
- `docs/handoff/integration-playbook.md`；
- `docs/handoff/common-errors.md`。

内容必须引用真实目录、命令、Schema、模拟模块和测试工具，不保留概念性占位。

### 任务10.2：框架维护文档

交付：

- 架构说明；
- 本地开发；
- 数据目录；
- 日志诊断；
- AI与知识库公共服务；
- 打包与发布；
- 版本回滚。

### 任务10.3：客户演示材料

交付：

- 5至10分钟演示脚本；
- 模拟文件；
- 三模块完整演示路线；
- 常见问题；
- 第一版已知限制。

### 任务10.4：发布`v0.1.0`

条件：

- 全部CI通过；
- 便携版和安装版验证通过；
- 文档完整；
- 无真实数据或密钥；
- `integration`向`main`的发布PR通过；
- 创建`v0.1.0`标签和发布说明。

## 15. 实施顺序和检查点

```text
检查点1：环境、远程仓库和integration分支可用
检查点2：协议、Schema、合同测试和三个模拟模块通过
检查点3：基础设施、模块运行器和状态机通过
检查点4：完整PySide6界面跑通三个模拟模块
检查点5：AI/知识公共接口和两阶段finalize闭环通过
检查点6：CI、便携版、安装版和干净环境通过
检查点7：交接文档、演示和v0.1.0发布完成
```

每个检查点完成后提交一个可运行版本，并更新`CHANGELOG.md`。不得在前一检查点失败时通过界面补丁绕过底层问题。

## 16. 开始编码前的操作性输入

以下不是设计变更，可以在对应阶段提供：

- 用户GitHub账号的已登录状态或仓库创建授权；
- 三名成员的GitHub用户名，用于邀请协作者；
- 真实API提供商和测试密钥，仅在AI真实调用验收时需要；
- Windows安装版发布者名称和可选数字签名，仅在正式发布时需要。

这些信息缺失不阻塞本地空框架、协议、模拟模块、UI和测试的开发。
