# 竹丝水分检测模块

这是 BambooWorkbench 的竹丝水分模块 v0.1.0。当前 T02 版本仅提供可静态发现的
模块包以及 `version`、`self-check` 健康命令，不包含水分检测算法，也尚未实现
T03 的 `run --job` 进程合同。

## 环境与安装

- Windows
- Python 3.11 或更高版本

模块当前没有第三方运行时依赖。可在模块目录中执行：

```powershell
python -m pip install -r requirements.txt
```

启动脚本只把模块自身的 `src` 目录加入 `PYTHONPATH`。宿主可用
`BAMBOO_MODULE_PYTHON` 指定 Python 可执行文件；否则脚本依次尝试 `py -3` 和
PATH 中的 `python`，不会访问网络。

## 当前命令

```powershell
.\run_module.bat version
.\run_module.bat self-check
```

`version` 的 stdout 只输出语义版本。`self-check` 将诊断写到 stderr。未知命令
返回退出码 2；缺少必要文件、导入失败或没有 Python 运行时返回退出码 4。

`run --job` 将在 T03 实现；当前调用会按未知命令处理，不能用于水分检测。
