# BambooWorkbench v1.1.0 本地发布清单

## 代码与测试

- [ ] 工作树仅包含本次正式版变更，产品与三个模块版本统一为 `1.1.0`
- [ ] `scripts/verify_repo.ps1` 全部通过
- [ ] 三个真实业务模块的合同、单元、集成与框架测试通过
- [ ] 正常启动默认加载真实模块，只有 `--demo` 使用 Mock
- [ ] GitHub `quality` 工作流绿色
- [ ] 仓库不包含企业真实数据、运行日志、数据库、密钥或客户本地路径

## 历史数据验收

- [ ] 竹丝水分 21 份历史文件处理成功，输入文件哈希不变
- [ ] 水煮实验 41 份历史文件处理成功，输入文件哈希不变
- [ ] 售后分析 13 份历史文件处理成功，采用案件去重、多标签可重复计数口径
- [ ] draft → 人工确认 → finalize 后不再残留待确认项
- [ ] 正式输出不泄露客户电脑绝对路径

## 便携版与安装版

- [ ] `scripts/build_portable.ps1` 和 `scripts/verify_portable.ps1` 通过
- [ ] `scripts/build_installer.ps1` 和 `scripts/verify_installer.ps1` 通过
- [ ] 清空 Python/PYTHONPATH 等环境变量后，真实模式与演示模式均可启动
- [ ] 安装包、桌面快捷方式和窗口使用 BambooWorkbench 图标
- [ ] 安装、覆盖升级、卸载后 `%LOCALAPPDATA%\BambooWorkbench` 数据保留
- [ ] 记录便携版、安装包 SHA-256

## 功能与客户验收

- [ ] 三个模块卡片、文件选择、进度、取消、结果和历史可用
- [ ] 模块人工确认可以 draft → finalize
- [ ] 知识库、AI 脱敏预览、联网授权与审计边界可演示
- [ ] DeepSeek/OpenAI 兼容接口可配置，密钥仅保存于 Windows 凭据管理器
- [ ] AI 不可用或拒绝后，本地确定性流程仍可继续
- [ ] 模块错误、错误 JSON 和超时不使桌面应用退出
- [ ] 客户验收指南和验收记录模板齐全

## 合并与发布

- [ ] 用户明确批准本次稳定版合并与发布
- [ ] 稳定分支 PR 到 `integration`，质量检查与评审通过
- [ ] `integration` PR 到 `main`，质量检查与评审通过
- [ ] `v1.1.0` 标签指向最终 `main` 提交
- [ ] package 工作流绿色，Release 仅上传该工作流生成的安装包、便携包和校验文件
- [ ] GitHub Release 标记 `v1.1.0` 为 Latest
