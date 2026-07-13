# BambooWorkbench v0.1.0 本地发布清单

## 代码与测试

- [ ] 工作树干净，版本为 `0.1.0`
- [ ] `scripts/verify_repo.ps1` 全部通过
- [ ] 三个模拟模块合同验证通过
- [ ] GitHub `quality` 工作流绿色（上传后执行）
- [ ] 没有企业真实数据、日志、数据库、密钥或本地路径

## 便携版与安装版

- [ ] `scripts/build_portable.ps1` 和 `verify_portable.ps1` 通过
- [ ] `scripts/build_installer.ps1` 和 `verify_installer.ps1` 通过
- [ ] 无 Python 的干净 Windows 10/11 完成启动与三模块自检
- [ ] 安装、覆盖升级、卸载后 `%LOCALAPPDATA%\BambooWorkbench` 数据保留
- [ ] 记录便携版/安装包 SHA-256

## 功能验收

- [ ] 三个模块卡片、文件选择、进度、取消、结果和历史可用
- [ ] 模块人工确认可以 draft→finalize
- [ ] 知识请求、模拟 AI、脱敏预览和授权审计可演示
- [ ] AI 拒绝后本地流程继续
- [ ] 模块错误、错误 JSON 和超时不使桌面应用退出
- [ ] 日志和结果目录可打开

## 文档与边界

- [ ] 模块开发指南、验收清单和 GitHub 流程与当前代码一致
- [ ] 客户演示脚本和空白验收记录齐全
- [ ] README 和 CHANGELOG 明确“空框架、不含真实业务算法”
- [ ] 已记录已知限制：Windows 第一版、模拟检索、真实 API 默认关闭、未签名安装包

## 发布授权

- [ ] 私有仓库、成员、分支保护已配置
- [ ] `integration` 向 `main` 的 PR 已评审
- [ ] 用户明确批准合并、创建 `v0.1.0` 标签和私有 Release

未完成最后一项前，不执行远程发布。
