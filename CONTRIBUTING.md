# 贡献指南

BambooWorkbench 已进入稳定维护阶段。任何代码、规则或文档变更都应从独立分支提交 Pull Request，并在合入前通过仓库质量门禁。

## 基本要求

- 不直接向 `main` 提交；
- 一个 Pull Request 只处理一个清晰主题；
- 保持模块公开合同、CLI、路径边界和离线降级兼容；
- 修改业务公式、阈值、字段映射或统计口径时，必须说明依据并补充回归测试；
- 不提交客户真实文件、个人信息、数据库、日志、API Key、Token 或本机绝对路径；
- 不通过降低断言、删除安全检查或跳过测试掩盖问题。

## 本地验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_repo.ps1
```

涉及安装、更新或目录结构时还需运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify_installer.ps1
```

Pull Request 应说明变更内容、风险、验证结果、兼容性影响和回滚方式。
