# BambooWorkbench 协作说明

本仓库采用 `main`（稳定版本）、`integration`（模块接入）和三个长期模块分支：

- `module/moisture`
- `module/boiling`
- `module/after-sales`

模块成员只修改本人负责的 `modules/<module_id>/`，并向 `integration` 提交 Pull Request。框架与仓库级修改通过独立工作分支提交；未经框架负责人确认，不直接推送 `main` 或改动其他模块。

提交前至少运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

Pull Request 必须说明变更范围、验证证据、人工判断边界、数据安全检查和回滚方式。任何测试材料都应使用模拟或脱敏数据，企业真实数据、客户信息、日志、数据库和密钥不得进入仓库。

完整模块要求见 [`docs/handoff/三个业务模块最终交接说明.md`](docs/handoff/三个业务模块最终交接说明.md)。
