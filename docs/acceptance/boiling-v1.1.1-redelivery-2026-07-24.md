# 水煮模块 v1.1.1 最小重新交付说明

对象：PR #54，`module/boiling -> integration`，已验收提交 `ca15d7a`。

## 当前结论

本轮功能和框架兼容性已通过：模块 48 项测试、Ruff、合同、version、self-check 通过；在该
提交上框架全量为 366 passed、8 项因 Windows 符号链接权限按条件跳过；真实 app smoke 和
`git diff --check` 通过。修改范围仅在 `modules/boiling/`，不需要 FCR。

唯一合并阻塞是模块仍报告 `1.1.0`，而项目负责人已明确本轮统一版本为 `1.1.1`。版本元数据
属于模块交付的一部分，不由框架负责人越界代改。

## 整改、验收和重新交付

1. 同步最新 `integration`（若 SHA 未变化可保留现状）。
2. 只在 `modules/boiling/` 将 manifest、运行时常量、README/CHANGELOG 等公开版本统一为
   `1.1.1`，不得顺带修改已验收业务逻辑。
3. 更新原 Draft PR #54，不要新建指向 `main` 的 PR。
4. 至少重跑模块 pytest、Ruff、静态合同、version、self-check 和 `git diff --check`。
5. 提供 PR 链接、最新完整 SHA、版本和测试结果。

禁止修改框架目录、其他模块、`integration` 或 `main`，禁止提交客户数据、密钥、缓存或运行
产物。版本补交无其他代码变更时，下一轮只做版本与快速回归复验，不重复本轮框架全量测试。

## 给水煮负责人的人类通知

你的最新提交 `ca15d7a` 已通过模块与框架兼容验收；目前只差将模块公开版本从 1.1.0 统一
更新为项目已确认的 1.1.1。请只做版本补交并更新原 Draft PR #54，不要改动已验收业务逻辑。

## 给水煮负责人 AI Agent 的执行提示词

```text
在 BambooWorkbench 的 module/boiling 分支上对 PR #54 做最小版本补交。同步最新 integration，
修改范围仅 modules/boiling/。不要改动 ca15d7a 已验收的 AI 建议和人工开裂复核逻辑；只把
module.json、运行时版本常量、README/CHANGELOG 等公开版本统一为 1.1.1。运行水煮完整 pytest、
Ruff、模块合同、run_module.bat version/self-check、git diff --check。更新原 Draft PR #54，
目标仍为 integration。完成后报告 PR、完整 SHA、版本和测试结果。
```
