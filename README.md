# BambooWorkbench（竹简工作台）

Windows本地品质数据桌面框架。第一版提供统一UI、模块协议和模拟模块，不实现三个业务模块的内部算法。

## Development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
