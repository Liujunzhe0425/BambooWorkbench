# BambooWorkbench 正式发布检查清单

## 版本与仓库

- [ ] 产品、三个模块、安装脚本、安装包和标签版本一致；
- [ ] 工作树干净，标签指向最终 `main` 提交；
- [ ] `scripts/verify_repo.ps1` 完整通过；
- [ ] 仓库不包含客户真实数据、个人信息、日志、数据库、API Key、Token 或本机绝对路径。

## 安装与数据

- [ ] `scripts/build_installer.ps1` 成功生成安装包；
- [ ] `scripts/verify_installer.ps1` 完成安装、源码/便携烟雾、覆盖更新、自动重启和卸载数据保留验证；
- [ ] 新安装创建空的 `source`、`output` 和三个输入导航子目录；
- [ ] 覆盖安装保留任务、历史、知识学习、设置、API Key 和用户成果。

## 功能与业务边界

- [ ] 三个模块的 draft → confirmation → finalize 合同通过；
- [ ] 月度正式结果、替换事务和后续月份累计重算通过；
- [ ] 待确认草稿、学习开关、学习证据撤销与重置通过；
- [ ] AI 拒绝、超时或不可用时，确定性处理安全降级；
- [ ] 业务成果由有权限的品质人员复核。

## Release 与自动更新

- [ ] `scripts/prepare_release.ps1` 生成安装包、便携包和 `SHA256SUMS.txt`；
- [ ] 主仓库 Release 为正式发布，不是 Draft 或 Pre-release；
- [ ] 安装包资产包含 GitHub 提供的 SHA-256 digest；
- [ ] 未配置 GitHub Token 时可发现、下载并校验更新；
- [ ] 下载进度到达 100%，覆盖当前目录后自动重启；
- [ ] Release 标记为 Latest。
