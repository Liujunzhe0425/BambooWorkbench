> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
# BambooWorkbench 竹丝水分模块迁移基线摘要

## 1. 记录范围

- Task：T00（Phase 0）。
- 记录日期：2026-07-15（Asia/Shanghai）。
- 正式开发分支：`module/moisture`。
- 基线提交：`1b961a1bf9c2966b568282828de3eb5b4c66cd2b`。
- 旧水分业务稳定来源提交：`d98433b`（本 Task 未读取或迁移其实现）。
- 本文只固定主框架、机器合同、mock 协议样板和测试证据；不创建正式模块，不修复框架，不迁移业务代码。

## 2. 仓库与运行环境

| 项目 | 基线值 |
|---|---|
| Git 分支 | `module/moisture` |
| Git HEAD | `1b961a1bf9c2966b568282828de3eb5b4c66cd2b` |
| Python | 仓库 `.venv\Scripts\python.exe`，3.12.7 |
| pytest | 8.4.2 |
| 操作系统 | Windows |

T00 开始时工作树已有以下未跟踪内容，均由其他任务产生并保持不动：

- 根目录 `竹丝水分模块重构实施计划.md`；
- 根目录 `迁移架构.md`；
- `modules/moisture/docs/migration/asset-map.md`；
- `modules/moisture/docs/migration/behavior-invariants.md`。

以上四个路径与 T00 的两个目标文件不冲突，均未清理、未修改、未暂存或纳入 T00 提交。本 Task 未执行 reset、checkout、stash 或历史改写。

## 3. 权威机器 Schema 指纹

哈希算法为 SHA-256，针对仓库中精确文件字节计算。

| 合同文件 | SHA-256 |
|---|---|
| `contracts/schemas/module-manifest.schema.json` | `313F7F894D6300BC5421E89B66AC3583A5B27C1983DE10400F0195E54E62A13F` |
| `contracts/schemas/job-request.schema.json` | `F84593EB8DF8FE9363C059AFCA62E0F80E67228BE54B1352FA674F0000305ABE` |
| `contracts/schemas/module-result.schema.json` | `05EF425E74EBB051039AFD167B27A016AAF1F5C32319BE8F8AD49CCF54127DB0` |

后续任务若观察到任一哈希变化，必须先重新审计合同，不得沿用本基线推断兼容性。

## 4. `mock_modules/moisture` 只读样板

### 4.1 Manifest

mock 的 `module.json` 声明：

| 字段 | 值 |
|---|---|
| `schema_version` | `1.0` |
| `module_id` | `moisture` |
| `module_version` | `0.1.0` |
| `entrypoint` | `run_module.bat` |
| `supported_extensions` | `[".xlsx"]` |
| `supports_single_file` | `true` |
| `supports_batch` | `true` |
| `supports_incremental` | `true` |
| `requires_network` | `false` |

`supports_incremental=true` 只是 mock 的既有声明，不是正式水分模块的业务依据。已批准架构要求正式模块声明 `supports_incremental=false`。

### 4.2 启动方式

`run_module.bat` 的既有行为：

1. 若存在 `BAMBOO_MODULE_HOST`，调用该 host 并传入 `--mock-module --module-id moisture`；
2. 否则从 PATH 调用 `python -m mock_modules.common.cli --module-id moisture`；
3. BAT 原样返回子进程退出码。

因此，脱离框架直接运行 BAT 时必须确保 PATH 中的 Python 已安装仓库依赖。未激活 `.venv` 的一次只读采样复现了 `ModuleNotFoundError: pydantic` 和退出码 1；把仓库 `.venv\Scripts` 临时置于当前进程 PATH 后，以下合同采样全部可复现。该观察是调用环境差异，不是合同断言失败。

### 4.3 三命令与输出通道

| 命令/场景 | stdout | stderr | 退出码 |
|---|---|---|---:|
| `version` | 单行 `0.1.0` | 空 | 0 |
| `self-check` | 单行 `ok` | 空 | 0 |
| `run` 缺少 `--job` | 空 | argparse 使用说明和缺参诊断 | 2 |
| `run --job <合法 draft>` | 仅两条 JSON Lines progress（25%、100%） | 空 | 0 |
| `run --job <非法 JSON>` | 空 | `invalid job request: ValidationError` | 2 |

合法 draft 采样还确认：

- `result.json` 可由 Python UTF-8 JSON 解析器读取；
- `status=success`；
- mock 登记 3 个 artifacts；
- 第一条 progress 为 25%，最后一条为 100%。

### 4.4 可复现 PowerShell 采样模板

以下模板从仓库根运行，不包含开发机或客户绝对路径。它只在系统临时目录创建空的合成 `.xlsx`、合法 draft job、非法 JSON 和输出目录；仓库 `.venv\Scripts` 仅临时加入当前进程 PATH。`PYTHONUTF8`、`PYTHONIOENCODING` 和显式 UTF-8 读写避免 PowerShell 默认代码页造成误判；每次调用分别保留 stdout、stderr 和退出码，并在 `finally` 中恢复环境和清理临时目录。

```powershell
$repo = (Resolve-Path .).Path
$runner = Join-Path $repo "mock_modules\moisture\run_module.bat"
$venvScripts = Join-Path $repo ".venv\Scripts"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("bamboo-moisture-mock-" + [guid]::NewGuid().ToString("N"))
$utf8 = New-Object Text.UTF8Encoding($false)
$oldPath = [Environment]::GetEnvironmentVariable("PATH", "Process")
$oldPythonUtf8 = [Environment]::GetEnvironmentVariable("PYTHONUTF8", "Process")
$oldPythonIoEncoding = [Environment]::GetEnvironmentVariable("PYTHONIOENCODING", "Process")

function Invoke-MockSample {
    param([Parameter(Mandatory = $true)][string[]]$CommandArgs)

    $sampleId = [guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $tempRoot ("stdout-" + $sampleId + ".txt")
    $stderrPath = Join-Path $tempRoot ("stderr-" + $sampleId + ".txt")
    $argumentLine = ($CommandArgs | ForEach-Object { '"' + $_ + '"' }) -join " "
    $process = Start-Process -FilePath $runner -ArgumentList $argumentLine `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = [IO.File]::ReadAllText($stdoutPath, $utf8)
        Stderr = [IO.File]::ReadAllText($stderrPath, $utf8)
    }
}

try {
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw "mock runner not found" }
    if (-not (Test-Path -LiteralPath (Join-Path $venvScripts "python.exe") -PathType Leaf)) { throw "repository venv not found" }
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    [Environment]::SetEnvironmentVariable("PATH", $venvScripts + [IO.Path]::PathSeparator + $oldPath, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Process")
    [Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "Process")

    $inputPath = Join-Path $tempRoot "synthetic.xlsx"
    $outputDir = Join-Path $tempRoot "output"
    $jobPath = Join-Path $tempRoot "job.json"
    $invalidJobPath = Join-Path $tempRoot "invalid-job.json"
    [IO.File]::WriteAllBytes($inputPath, [byte[]]@())
    $job = [ordered]@{
        schema_version = "1.0"
        job_id = "mock-baseline-001"
        module_id = "moisture"
        phase = "draft"
        run_mode = "single"
        input_files = @($inputPath)
        output_dir = $outputDir
    }
    [IO.File]::WriteAllText($jobPath, ($job | ConvertTo-Json -Depth 5), $utf8)
    [IO.File]::WriteAllText($invalidJobPath, "{not-json", $utf8)

    $version = Invoke-MockSample -CommandArgs @("version")
    $selfCheck = Invoke-MockSample -CommandArgs @("self-check")
    $missingJob = Invoke-MockSample -CommandArgs @("run")
    $validJob = Invoke-MockSample -CommandArgs @("run", "--job", $jobPath)
    $invalidJob = Invoke-MockSample -CommandArgs @("run", "--job", $invalidJobPath)

    $progress = @($validJob.Stdout -split "`r?`n" | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
    $result = [IO.File]::ReadAllText((Join-Path $outputDir "result.json"), $utf8) | ConvertFrom-Json
    if ($version.ExitCode -ne 0 -or $version.Stdout.Trim() -ne "0.1.0" -or $version.Stderr) { throw "version sample mismatch" }
    if ($selfCheck.ExitCode -ne 0 -or $selfCheck.Stdout.Trim() -ne "ok" -or $selfCheck.Stderr) { throw "self-check sample mismatch" }
    if ($missingJob.ExitCode -ne 2 -or $missingJob.Stdout -or -not $missingJob.Stderr) { throw "missing-job sample mismatch" }
    if ($validJob.ExitCode -ne 0 -or $validJob.Stderr -or $progress.Count -ne 2 -or $progress[0].percent -ne 25 -or $progress[-1].percent -ne 100) { throw "valid-job sample mismatch" }
    if ($result.status -ne "success" -or $result.outputs.Count -ne 3) { throw "result.json sample mismatch" }
    if ($invalidJob.ExitCode -ne 2 -or $invalidJob.Stdout -or -not $invalidJob.Stderr) { throw "invalid-json sample mismatch" }

    @(
        [pscustomobject]@{ Sample = "version"; ExitCode = $version.ExitCode; Stdout = $version.Stdout; Stderr = $version.Stderr }
        [pscustomobject]@{ Sample = "self-check"; ExitCode = $selfCheck.ExitCode; Stdout = $selfCheck.Stdout; Stderr = $selfCheck.Stderr }
        [pscustomobject]@{ Sample = "run missing --job"; ExitCode = $missingJob.ExitCode; Stdout = $missingJob.Stdout; Stderr = $missingJob.Stderr }
        [pscustomobject]@{ Sample = "run valid job"; ExitCode = $validJob.ExitCode; Stdout = $validJob.Stdout; Stderr = $validJob.Stderr }
        [pscustomobject]@{ Sample = "run invalid JSON"; ExitCode = $invalidJob.ExitCode; Stdout = $invalidJob.Stdout; Stderr = $invalidJob.Stderr }
    ) | Format-List
    [pscustomobject]@{ ResultStatus = $result.status; ArtifactCount = $result.outputs.Count } | Format-List
}
finally {
    [Environment]::SetEnvironmentVariable("PATH", $oldPath, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONUTF8", $oldPythonUtf8, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONIOENCODING", $oldPythonIoEncoding, "Process")
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
```

### 4.5 mock 源码中的代表性故障行为

只读检查 `mock_modules/common/cli.py` 和 `scenarios.py` 得到：

- job 读取、Schema/model 校验、module ID 或 finalize confirmation 不合法时返回 2；
- mock 内部未处理异常或 `crash` 场景返回 3；
- `timeout` 场景休眠 120 秒，预期由宿主超时控制；
- `invalid` 场景故意写入非法 `result.json` 后返回 0，用于验证宿主结果校验；
- `confirm`、`partial`、`fail`、`ai`、`knowledge` 是测试场景，不得作为正式水分业务实现；
- mock 未定义正式模块约定的环境缺失退出码 4 行为。

## 5. 框架门禁组成

`scripts/verify_repo.ps1` 按顺序执行：

1. `ruff check app core ui mock_modules scripts tests`；
2. `pytest -q`；
3. 验证 moisture、boiling、after_sales 三个 mock 模块合同；
4. `git diff --check`。

脚本优先使用仓库 `.venv`，在任一步非零时停止。T00 的完整执行结果见 `baseline-tests.md`。

## 6. 基线结论与关注项

- 本次复核的合同/单元、逐文件 integration 和完整仓库门禁均未出现 pytest 断言失败。
- 完整门禁在 1900 秒上限内以 807.178 秒完成并退出 0，未发生外部超时，也未发生门禁进程错误。
- 8 个完整门禁 skip 均由当前 Windows 环境缺少符号链接权限导致。
- 逐文件 integration 及完整门禁退出后各出现一次 pytest-qt/Windows COM `0x8001010d` fatal diagnostic；对应命令仍返回 0、pytest 汇总完整、门禁明确报告通过。该诊断作为环境关注项保留，不在 T00 修复。
- mock 合并采样包装命令曾在启动 mock 前被本机防病毒策略拦截，拆分命令后所有采样通过；Windows 重定向 stdout 的本地代码页也不等同于 UTF-8。二者均是采样工具/环境关注项，不是 mock 合同失败。
- 直接 BAT 的 Python 解析依赖 PATH；正式模块实现和打包时需由后续 Task 按主框架运行环境处理，不得硬编码开发机 Python 路径。
- 文档未包含客户数据、密钥、凭据、个人绝对路径或原始长日志。
