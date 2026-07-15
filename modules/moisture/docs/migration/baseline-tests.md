# BambooWorkbench 主框架基线测试证据

## 1. 证据分类规则

本记录把结果严格区分为：

- **断言失败**：pytest 收集并执行测试后报告 failed/error；
- **进程错误**：测试或门禁进程非零退出，但不是外部计时器终止；
- **外部超时**：外层执行器达到明确上限后终止仍在运行的命令；
- **通过并有环境关注项**：退出码为 0 且测试汇总通过，但存在 skip 或退出后的平台诊断。

历史全量 pytest 曾在约 604 秒被外部终止，只能分类为“旧外部超时/时限不足”，不能据此声称存在断言失败。T00 重新使用逐文件 integration 和 1900 秒门禁上限建立了可判定证据。

## 2. 预检

| 检查 | 命令 | 结果 |
|---|---|---|
| 分支 | `git branch --show-current` | `module/moisture` |
| 工作树 | `git status --short` | 存在预先已有且不冲突的未跟踪计划/T01 文档；未清理 |
| HEAD | `git rev-parse HEAD` | `1b961a1bf9c2966b568282828de3eb5b4c66cd2b` |
| Python 路径 | `.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"` | 来自仓库 `.venv` |
| Python 版本 | `.\.venv\Scripts\python.exe --version` | 3.12.7 |
| pytest | `.\.venv\Scripts\python.exe -m pytest --version` | 8.4.2 |

## 3. 合同和单元测试

命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contract tests\unit -q
```

结果：

| 指标 | 值 |
|---|---:|
| 退出码 | 0 |
| passed | 109 |
| skipped | 2 |
| failed/error | 0 |
| pytest 报告耗时 | 36.22 秒 |
| 外部测量耗时 | 38.030 秒 |

两个 skip 均为 Windows 当前用户不具备创建符号链接权限：

- `tests/unit/modules/test_process_runner_boundaries.py` 的真实符号链接边界；
- `tests/unit/platform/test_path_safety.py` 的真实符号链接边界。

分类：**通过并有环境 skip**；不是断言失败、进程错误或外部超时。

## 4. Integration 逐文件结果

每个文件均使用以下形式独立启动，不合并为一次 pytest 收集：

```powershell
.\.venv\Scripts\python.exe -m pytest <tests\integration\test_*.py> -q
```

| 测试文件 | passed | skipped | failed/error | pytest 耗时 | 外部耗时 | 退出码 |
|---|---:|---:|---:|---:|---:|---:|
| `test_confirmation_flow.py` | 34 | 4 | 0 | 207.87 秒 | 209.792 秒 | 0 |
| `test_fault_isolation.py` | 13 | 0 | 0 | 54.27 秒 | 58.468 秒 | 0 |
| `test_process_runner.py` | 32 | 0 | 0 | 146.60 秒 | 148.647 秒 | 0 |
| `test_restart_recovery.py` | 22 | 2 | 0 | 138.76 秒 | 140.946 秒 | 0 |
| `test_service_request_flow.py` | 6 | 0 | 0 | 21.72 秒 | 23.390 秒 | 0 |
| `test_task_service.py` | 14 | 0 | 0 | 63.05 秒 | 64.767 秒 | 0 |
| **合计** | **121** | **6** | **0** | — | **646.010 秒** | **全部为 0** |

6 个 skip 均为 confirmation/restart recovery 中需要真实 Windows 符号链接权限的安全测试。

批处理完成后打印了一次 pytest-qt/Windows COM fatal diagnostic（代码 `0x8001010d`），但六个独立 pytest 均已输出完整通过汇总、逐项退出码均为 0，外层批处理也返回 0。分类：**测试通过，伴随非阻塞进程诊断**。

## 5. 完整仓库门禁

命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_repo.ps1
```

执行约束：外层上限为 1900 秒（31 分 40 秒），满足“至少 30 分钟”。本次复核持续等待同一个门禁进程直至完成，没有中断或重新启动。

结果：

| 指标 | 值 |
|---|---:|
| 退出码 | 0 |
| ruff | `All checks passed!` |
| pytest passed | 307 |
| pytest skipped | 8 |
| pytest failed/error | 0 |
| pytest 报告耗时 | 801.15 秒 |
| 门禁外部测量耗时 | 807.178 秒 |
| 外部超时 | 否 |
| mock 合同验证 | 三个 mock 均通过（脚本最终继续完成） |
| `git diff --check` | 通过（脚本最终继续完成） |
| 脚本最终消息 | `Repository verification passed.` |

8 个 skip 是逐文件结果中的 6 个 integration 符号链接 skip，加上 2 个 unit 符号链接 skip。

门禁退出后再次打印 pytest-qt/Windows COM fatal diagnostic（代码 `0x8001010d`）；证据同时显示 pytest 汇总完整、后续三个 mock 合同验证和 `git diff --check` 已完成、脚本打印通过消息并返回 0。因此分类为：**仓库门禁通过，伴随非阻塞平台诊断**，不是断言失败、进程错误或外部超时。

## 6. mock 命令采样

采样使用系统临时目录中的合成文件，不使用客户数据；临时目录在采样后删除。

| 采样 | 结果 |
|---|---|
| PATH 未指向 `.venv` 时直接调用 BAT | exit 1，系统 Python 缺少 `pydantic`；环境错误 |
| PATH 临时包含仓库 `.venv\Scripts` 后 `version` | exit 0，stdout 单行 `0.1.0`，stderr 空 |
| 同环境 `self-check` | exit 0，stdout 单行 `ok`，stderr 空 |
| `run` 缺 `--job` | exit 2，stdout 空，stderr 为 argparse 诊断 |
| 合法 draft `run --job` | exit 0，stdout 仅 25%/100% 两条 JSON Lines，stderr 空 |
| 成功 result | UTF-8 JSON 可解析，`status=success`，3 个 artifacts |
| 非法 JSON job | exit 2，stdout 空，stderr 为 ValidationError 摘要 |

一次用于合并采样的 PowerShell 包装命令在启动 mock 前被本机防病毒策略拦截；拆分为简单命令后逐项复核均得到表中结果。另一次用 UTF-8 强制解码 Windows 重定向的 stdout 时遇到本地代码页不匹配；直接检查通道内容仍确认两条合法 JSON Lines。两项均属于采样工具/环境关注项，不是 mock 断言失败、mock 进程错误或外部超时。

## 7. 可复现结论

- 当前基线没有已知 pytest 断言失败。
- 当前完整门禁没有进程错误，退出码为 0。
- 当前完整门禁在 1900 秒上限内结束，没有外部超时。
- Windows 符号链接权限造成 8 个明确 skip。
- pytest-qt/Windows COM 退出诊断需要后续框架维护者关注，但 T00 证据不足以把它判为测试失败，也不授权在模块分支修复框架。
