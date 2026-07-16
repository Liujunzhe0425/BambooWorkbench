# 竹丝水分检测模块

这是 BambooWorkbench 的竹丝水分模块 v0.1.0。模块提供可静态发现的模块包、
`version`、`self-check` 健康命令以及 `run --job` 启动合同；当前仍不包含水分检测算法。

## 环境与安装

- Windows
- Python 3.11 或更高版本

所有开发和测试命令必须显式使用当前 BambooWorkbench 仓库的虚拟环境。开始前验证：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pytest --version
```

开发与测试所用解释器必须属于该仓库的 `.venv`，不得使用裸 `python`、`py`、
系统 Python 或全局安装的依赖。`jsonschema` 是模块的 Schema 校验依赖；紧随其后的 `requirements.txt` 安装命令会安装该依赖。

```powershell
.\.venv\Scripts\python.exe -m pip install -r modules\moisture\requirements.txt
```

依赖必须预先存在于所选虚拟环境；启动器既不安装依赖，也不访问网络。

启动脚本只把模块自身的 `src` 目录加入 `PYTHONPATH`。解释器选择顺序固定为：

1. 宿主通过 `BAMBOO_MODULE_PYTHON` 显式指定的解释器；
2. 已激活 `VIRTUAL_ENV` 下的 `Scripts\python.exe`；
3. BambooWorkbench 仓库 `.venv\Scripts\python.exe`；
4. 模块本地 `.venv\Scripts\python.exe`。

显式解释器或已激活环境不存在、低于 Python 3.11，或不能导入 `jsonschema` 时，
启动器立即返回退出码 4，不会偷偷切换到其他环境。未声明前两项时，仓库和模块
虚拟环境按上述顺序探测；均不合格时返回 4。启动器绝不从 PATH 选择 `python`
或 `py`。

## 当前命令

```powershell
.\run_module.bat version
.\run_module.bat self-check
.\run_module.bat run --job C:\absolute\path\to\job.json
```

`version` 的 stdout 只输出语义版本。`self-check` 将诊断写到 stderr。未知命令
返回退出码 2；缺少必要文件、导入失败或没有 Python 运行时返回退出码 4。

`run --job` 当前只执行启动合同校验并生成引导结果，尚不执行水分检测算法。
