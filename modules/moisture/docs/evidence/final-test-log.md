# Gate D 最终测试摘要

执行日期：2026-07-17  
运行时提交：`9d55676`  
解释器：当前 BambooWorkbench 仓库 `.venv`，Python 3.12.7

| 门禁 | 结果 |
|---|---|
| `module_contract_cli validate modules/moisture` | 通过 |
| `pytest modules/moisture/tests -q` | 282 passed |
| `scripts/verify_repo.ps1` 根测试 | 315 passed, 8 skipped |
| `scripts/verify_repo.ps1` 模块测试 | 282 passed |
| 仓库 lint、合同与 `git diff --check` | 通过 |

8 个 skip 均为当前 Windows 用户缺少创建 symlink 的权限；对应测试明确记录
`WinError 1314`，不是业务、合同或普通路径隔离失败。

Gate D 首次执行发现 `verify_repo.ps1` 将中文仓库路径中的 `sys.executable` 经
PowerShell 文本管道误码。修复提交 `9d55676` 改为在仓库 Python 进程内使用
`os.path.samefile` 判定解释器，随后完整 Gate D 通过；未降低解释器约束。
