> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
# 第三轮整改：Codex 与 Claude Code + DeepSeek 协同实施方案

## 1. 方案目的

本方案依据《竹丝水分检测模块第三轮整改与重新交付说明-2026-07-19.md》制定，只解决水分模块安装版缺少独立运行时的问题。

固定目标：

> 让 `dist/BambooWorkbench/modules/moisture/run_module.bat` 在客户电脑没有 Python、没有 `.venv`、没有开发环境变量时，仍能自动运行冻结的正式水分模块。

本轮不得修改水分公式、统计、规则、颜色、经验适用性、AI 响应校验或 draft/finalize 业务语义。

## 2. 当前基线

| 项目 | 基线 |
| --- | --- |
| 业务分支 | `module/moisture` |
| 已通过业务提交 | `3850318` |
| 最新 integration | `a3afa43` |
| integration 合并提交 | `23d3f0d` |
| Python 开发环境 | 仓库 `.venv`，Python 3.12.7，兼容模块的 Python 3.11+ 要求 |
| 已通过业务基线 | 模块 `301 passed`、历史表 21/21、样本 166、真实 draft/finalize 闭环通过 |
| PR | 继续更新 Draft PR #15，目标为 `integration` |

最新 integration 已提供主框架侧合同：

- `scripts/build_portable.ps1` 在主程序打包后调用真实模块运行时构建器；
- `scripts/build_real_module_runtimes.ps1` 要求每个正式模块提供 `build_portable_runtime.ps1`；
- `scripts/verify_portable.ps1` 会在清空开发环境后执行正式模块的 `version` 和 `self-check`；
- CI 已改为从仓库 `.venv` 执行门禁。

因此本轮原则上只修改 `modules/moisture/`。如果发现 integration 的公共钩子合同存在缺陷，应停止并交给框架负责人处理，不在水分模块任务中越界修改 `.github/`、`scripts/`、`app/`、`core/` 或 `ui/`。

## 3. 为什么必须混合执行

独立运行时涉及 PyInstaller、资源定位、BAT 启动优先级、构建目录清理和无 Python 环境进程验证，属于高风险交付链，必须由 Codex掌握核心设计和最终门禁。

以下工作边界清晰，适合 Claude Code + DeepSeek：

- 按已经确定的合同补局部静态测试；
- 补充仓库卫生检查；
- 更新 README、CHANGELOG 和交付说明；
- 根据 Codex提供的真实测试结果整理验收记录。

小模型不得自行选择冻结架构、改变 BAT 回退策略或修改公共打包脚本。

## 4. 总体分工

| 工作项 | 执行者 | 原因 |
| --- | --- | --- |
| integration 合同核对与风险分析 | Codex | 涉及主框架与模块交界 |
| 冻结布局和资源收集方案 | Codex | 影响 Schema、规则、经验、模板定位 |
| `build_portable_runtime.ps1` 核心实现 | Codex | 涉及路径安全、清理和可重复构建 |
| `run_module.bat` 自动发现冻结程序 | Codex | 入口合同和退出码风险高 |
| 冻结入口及 `runtime_paths` 必要适配 | Codex | 影响源码与 frozen 双运行模式 |
| 构建钩子静态/卫生测试 | CC + DeepSeek | 修改边界小、期望明确 |
| README、CHANGELOG、交付文档 | CC + DeepSeek | 纯文档、可独立验收 |
| 真实 portable 构建 | Codex | 时间较长且跨主框架打包链 |
| 无 Python 环境 version/self-check | Codex | 必须验证真实进程环境隔离 |
| portable draft/finalize 闭环 | Codex | 涉及身份、成果和正式进程合同 |
| 最终差异审查和回归决策 | Codex | 防止业务基线退化 |
| PR #15 推送、状态和合并批准 | 用户/负责人 | 外部仓库操作和审批责任 |

## 5. 推荐冻结设计基线

以下设计由 Codex在实施时确认，CC 不得自行改变：

1. 使用 PyInstaller **onedir** 方式构建 `BambooMoistureModule.exe`，优先保证资源透明、启动稳定和问题可诊断；
2. 运行时安装到：

   ```text
   dist/BambooWorkbench/modules/moisture/runtime/
   ```

3. `run_module.bat` 在没有显式 `BAMBOO_MODULE_EXECUTABLE` 时，自动检查模块自己的：

   ```text
   runtime/BambooMoistureModule.exe
   ```

4. 源码仓库中不存在 `runtime/` 时，BAT 继续使用可信 `BAMBOO_MODULE_PYTHON`、`VIRTUAL_ENV`、仓库 `.venv` 或模块 `.venv`；
5. BAT 继续禁止裸 `python`、`py` 和系统 Python 回退；
6. 冻结运行时内部必须包含：

   - `schemas/`；
   - `rules/active/`；
   - `experience/`；
   - `templates/`；
   - 模块 CLI 及其 Python 依赖。

7. frozen 模式继续通过 `runtime_paths.module_root()` 获取只读资产根；不得把开发机绝对路径写进程序、结果或报告；
8. 构建钩子只能删除仓库自己的模块构建工作目录，以及便携包内本模块的 `runtime/`；不得清理整个 `dist`、其他模块或用户目录；
9. 构建钩子不得自动安装全局依赖；缺少 PyInstaller 或仓库 `.venv` 时应明确失败；
10. `.exe`、`runtime/`、`build/`、`dist/`、`.venv` 不得进入 Git。

如果实施验证证明 onedir 与现有 `runtime_paths` 不兼容，Codex可以在不改变外部 BAT 合同的前提下调整冻结内部布局，并在验收记录中说明原因。该决策不得下放给 CC。

## 6. 分阶段执行计划

### R3-C0：Codex 基线和合同冻结

执行者：Codex。

只读检查：

- 第三轮整改说明；
- `scripts/build_real_module_runtimes.ps1`；
- `scripts/build_portable.ps1`；
- `scripts/verify_portable.ps1`；
- `modules/moisture/run_module.bat`；
- `modules/moisture/src/moisture/runtime_paths.py`；
- 当前打包、合同和离线输出测试。

产出：

- 确认冻结入口、目标目录和资源映射；
- 确认 BAT 自动发现顺序；
- 列出允许删除的构建路径；
- 确认不需要修改主框架文件。

停止条件：

- 主框架钩子不能把模块运行时安装到正式便携目录；
- 公共验证脚本与模块入口合同冲突；
- 必须修改官方 Schema 才能完成。

### R3-C1：Codex 实现独立运行时

执行者：Codex。

允许修改：

- `modules/moisture/build_portable_runtime.ps1`；
- `modules/moisture/run_module.bat`；
- 必要的模块冻结入口或 `runtime_paths.py`；
- 与核心冻结行为直接相关的少量测试。

实现要求：

1. 构建钩子验证仓库 `.venv` 和 PyInstaller；
2. 所有计算路径解析为仓库内绝对路径，并在删除前做边界检查；
3. 可重复构建，旧的本模块 runtime 可安全替换；
4. 收集 Schema、规则、经验和模板；
5. BAT 自动选择随模块交付的 EXE；
6. 显式 `BAMBOO_MODULE_EXECUTABLE` 仍具有最高优先级；
7. 源码开发运行方式不退化；
8. 退出码、stdout/stderr 协议不变。

Codex先运行最小检查，不立即跑全部模块测试：

```powershell
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests\contract\test_cli_health.py -q
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules\moisture
```

### R3-S1：CC + DeepSeek 补局部构建边界测试

执行者：Claude Code + DeepSeek。必须在 R3-C1 的冻结布局已经由 Codex固定后执行。

唯一目标：补充不执行真实长时间打包的局部测试，验证构建钩子合同和仓库卫生，不改核心实现。

允许修改：

- `modules/moisture/tests/contract/test_portable_runtime_build.py`；
- 如已有同职责测试文件，则只修改该文件。

建议代表性测试：

- 构建钩子存在并引用仓库 `.venv`；
- 输出目标限定在 `dist/BambooWorkbench/modules/moisture/runtime`；
- 脚本包含删除前的仓库边界检查；
- BAT 包含本地冻结程序发现路径；
- 代码和 manifest 不引用开发机绝对路径；
- Git 跟踪文件中不存在 `.exe`、模块 runtime、build、dist 或 `.venv` 产物。

禁止：

- 修改 `run_module.bat` 和构建钩子；
- 修改 `.github/`、`scripts/`、`app/`、`core/`、`ui/`；
- 自行增加 PyInstaller 参数或改变 runtime 布局；
- 运行真实 `scripts/build_portable.ps1`；
- 运行全仓 pytest。

定向测试：

```powershell
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests\contract\test_portable_runtime_build.py -q
git diff --check
```

同一错误最多两轮修复，仍失败立即交回 Codex。

### R3-S2：CC + DeepSeek 更新使用和交付文档

执行者：Claude Code + DeepSeek。与 R3-S1 顺序执行，不并行修改共享工作区。

允许修改：

- `modules/moisture/README.md`；
- `modules/moisture/CHANGELOG.md`；
- 第三轮整改验收记录文档。

文档必须明确：

- 源码开发使用仓库 `.venv`；
- 客户便携版/安装版不需要 Python；
- 构建命令和 runtime 目标目录；
- BAT 的正式运行时选择顺序；
- 不允许提交冻结程序和构建产物；
- 不声称尚未运行的 portable 或端到端验证已经通过。

小模型只记录 Codex提供的真实测试数字，不得编造截图、命令输出或通过状态。

### R3-C2：Codex 审查小模型改动

执行者：Codex。

审查重点：

- 小模型是否越过允许文件范围；
- 测试是否只是检查字符串而遗漏真实行为；
- 是否错误放宽 BAT 或路径安全策略；
- 是否引入裸 Python、全局依赖或绝对路径；
- 文档是否把“计划验证”写成“已经通过”。

发现问题时只修对应责任边界，不重新设计已稳定的业务算法。

### R3-C3：Codex 真实 portable 与隔离环境验证

执行者：Codex。

先验证解释器：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pytest --version
```

然后按成本递增执行：

1. 模块 Ruff 和合同测试；
2. 构建模块运行时；
3. 执行主框架 portable 构建；
4. 在清空 `BAMBOO_MODULE_EXECUTABLE`、`BAMBOO_MODULE_PYTHON`、`VIRTUAL_ENV` 且 PATH 不含 Python 的子进程中验证：
   - `run_module.bat version`；
   - `run_module.bat self-check`；
5. 使用脱敏最小样本执行 portable draft；
6. 使用已有确认和 AI denied fixture 执行独立 portable finalize；
7. 验证 `result.json`、XLSX、Markdown、输入哈希和 stdout/stderr；
8. 最后运行模块回归和必要的便携门禁。

真实 portable 闭环必须由正式 BAT 和冻结 EXE 完成，不能直接 import 模块 orchestrator 代替。

### R3-S3：CC + DeepSeek 整理验收记录

执行者：Claude Code + DeepSeek。

输入只能使用 Codex提供的脱敏命令结果、测试数字和截图路径。输出一份简短验收记录，包括：

| 项目 | 记录内容 |
| --- | --- |
| 构建命令 | 实际命令 |
| version/self-check | 退出码和摘要 |
| portable draft/finalize | 状态和成果 |
| 模块测试 | 实际通过数量 |
| 历史基线 | 21/21、166，是否退化 |
| Git 卫生 | 是否出现 EXE/runtime/build/dist/.venv |
| 未解决问题 | 明确列出 |

不得把 API Key、客户原表、真实供应商身份、本机绝对路径或完整运行日志交给 DeepSeek。

### R3-C4：Codex 最终门禁和交接

执行者：Codex。

最终确认：

- 业务提交 `3850318` 的确定性结果不退化；
- source 与 portable 的 version、self-check 和任务合同一致；
- frozen 运行时不依赖 Python 或开发变量；
- 规则、经验、Schema 和模板均从冻结资源正确读取；
- draft/finalize 是两个真实独立进程；
- AI denied 安全降级；
- 没有 Provider、API Key 或网络逻辑进入 moisture；
- Git 中没有冻结产物；
- 只存在计划内源码和文档修改。

完成后停止，不 push、不把 PR 转为 Ready、不合并 PR #15。由用户根据验收材料自行推送和通知负责人。

## 7. CC + DeepSeek 可直接使用的任务文本

### 7.1 局部测试任务

```text
请读取：
- modules/moisture/build_portable_runtime.ps1
- modules/moisture/run_module.bat
- modules/moisture/tests/contract 中与 launcher、依赖边界相关的测试

本次唯一目标：按照已经确定的 portable runtime 布局，补充构建钩子与仓库卫生的局部测试。

只允许修改：
- modules/moisture/tests/contract/test_portable_runtime_build.py

禁止修改正式代码、主框架、官方 Schema、工作流和公共打包脚本。不要改变 runtime 布局，不运行真实 portable 构建，不运行全仓测试。

所有 Python 命令必须使用：
.\.venv\Scripts\python.exe

只运行该测试文件和 git diff --check。同一错误最多修复两轮，仍失败立即停止，汇报责任范围和最小建议。不提交、不 push。
```

### 7.2 文档任务

```text
请读取第三轮整改说明、当前 README、CHANGELOG，以及 Codex提供的实际测试结果。

本次唯一目标：更新水分模块源码运行、portable 运行和第三轮交付说明。

只允许修改：
- modules/moisture/README.md
- modules/moisture/CHANGELOG.md
- 指定的第三轮验收记录

不得修改代码或测试，不得声称未执行的测试已经通过，不得写入客户信息、API Key、本机绝对路径和完整日志。不提交、不 push。
```

## 8. Git 与共享工作区规则

Codex 和 CC + DeepSeek 不得同时编辑同一工作区。固定顺序为：

```text
Codex 核心实现
→ CC 局部测试
→ CC 文档
→ Codex 统一审查和真实构建
→ CC 整理验收记录
→ Codex 最终门禁
```

每次交接前必须提供：

- `git status --short`；
- 当前提交号；
- 允许接手修改的文件；
- 已运行测试；
- 未解决问题。

禁止自动 `stash`、`reset`、`clean`，禁止 `git add -A`。已有用户文件和未跟踪整改文档必须保留。

建议提交顺序：

1. `build(moisture): add standalone portable runtime`；
2. `test(moisture): cover portable runtime boundaries`；
3. `docs(moisture): record third-round portable acceptance`。

如果希望保持第三轮原说明中的单提交形式，可在最终推送前由用户决定是否整理提交；模型不得擅自改写已共享历史。

## 9. 测试额度控制

- CC 每个任务只运行 1 个定向测试文件；
- Codex 在核心实现阶段只运行 launcher/contract 定向测试；
- 真实 portable 构建只在核心代码审查通过后执行；
- 模块 `301` 项回归每批最多执行一次；
- 历史 21 份表回归在最终门禁执行一次；
- 全仓门禁优先交给 GitHub Actions，本地不反复运行；
- 同一错误最多两轮自主修复，仍不能解释时停止并汇报。

## 10. 完成标准

只有以下条件全部满足，第三轮整改才可标记完成：

- `build_portable_runtime.ps1` 存在、可重复执行且不越界；
- portable BAT 能自动发现本模块冻结程序；
- 无 Python 环境下 version 和 self-check 成功；
- 脱敏 portable draft/finalize 闭环成功；
- Schema、规则、经验和模板均可读取；
- 确定性业务结果与历史基线一致；
- 模块测试通过；
- Git 中没有 EXE、runtime、build、dist 或 `.venv`；
- 验收记录只包含真实结果；
- 用户尚未批准前，PR #15 保持 Draft 且不合并。
