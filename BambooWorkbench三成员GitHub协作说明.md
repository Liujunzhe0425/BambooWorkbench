# BambooWorkbench 三个业务模块 GitHub 协作说明

## 1. 协作目标

三位成员分别在自己的模块分支和模块目录中开发，不直接修改公共框架代码，也不直接操作 `main` 与 `integration` 分支。

模块完成后，成员通过 Pull Request（PR）提交到 `integration`，由项目负责人审核、测试和合并。通过整体测试后，再由项目负责人将 `integration` 合并到 `main`。

## 2. 分工与修改范围

| 负责模块 | 专属分支 | 允许修改的目录 | PR 目标分支 |
|---|---|---|---|
| 原竹丝水分检测 | `module/moisture` | `modules/moisture/` | `integration` |
| 水煮实验 | `module/boiling` | `modules/boiling/` | `integration` |
| 售后分析 | `module/after-sales` | `modules/after_sales/` | `integration` |

三位成员不得自行修改以下内容：

- `app/`
- `core/`
- `ui/`
- `contracts/`
- `.github/`
- `packaging/`
- `resources/`
- `logo/`
- 其他成员负责的 `modules/` 目录
- `main` 和 `integration` 分支中的代码

如果业务实现确实需要调整公共接口或框架代码，请先联系项目负责人，不要直接修改。

## 3. 第一次下载项目

三位成员均先执行：

```powershell
git clone https://github.com/Liujunzhe0425/BambooWorkbench.git
Set-Location BambooWorkbench

git config user.name "自己的GitHub用户名"
git config user.email "自己的GitHub邮箱"
```

### 3.1 原竹丝水分检测成员

```powershell
git switch module/moisture
git pull --ff-only origin module/moisture
```

### 3.2 水煮实验成员

```powershell
git switch module/boiling
git pull --ff-only origin module/boiling
```

### 3.3 售后分析成员

```powershell
git switch module/after-sales
git pull --ff-only origin module/after-sales
```

切换后必须确认当前分支：

```powershell
git branch --show-current
git status
```

显示的分支名称必须与本人负责的分支一致，确认无误后再开始开发。

## 4. 每次开始开发前

先切换到自己的分支并获取最新代码。以水分检测模块为例：

```powershell
git switch module/moisture
git pull --ff-only origin module/moisture
git status
```

水煮实验和售后分析成员将分支名称替换为自己的专属分支。

如果 `git status` 显示存在来源不明的未提交改动，请先停止操作并联系项目负责人。

## 5. 提交代码

只添加自己负责的模块目录，不要使用 `git add .`。

### 5.1 原竹丝水分检测模块

```powershell
git add modules/moisture
git status
git diff --cached --name-only
git commit -m "feat(moisture): 简要说明本次完成的功能"
git push origin module/moisture
```

### 5.2 水煮实验模块

```powershell
git add modules/boiling
git status
git diff --cached --name-only
git commit -m "feat(boiling): 简要说明本次完成的功能"
git push origin module/boiling
```

### 5.3 售后分析模块

```powershell
git add modules/after_sales
git status
git diff --cached --name-only
git commit -m "feat(after-sales): 简要说明本次完成的功能"
git push origin module/after-sales
```

在执行 `git commit` 前，请重点检查：

```powershell
git diff --cached --name-only
```

输出结果中只能出现本人模块目录下的文件。如果出现公共框架、其他模块或其他无关文件，暂时不要提交，并联系项目负责人处理。

## 6. 创建 Pull Request

成员将代码推送到专属分支后，在 GitHub 仓库页面创建 Pull Request。

设置规则如下：

- `base`：必须选择 `integration`
- `compare`：选择本人专属模块分支
- 不得直接向 `main` 创建 PR
- 不得自行合并 PR

对应关系：

| 模块 | base | compare |
|---|---|---|
| 原竹丝水分检测 | `integration` | `module/moisture` |
| 水煮实验 | `integration` | `module/boiling` |
| 售后分析 | `integration` | `module/after-sales` |

PR 标题示例：

```text
[水分检测] 完成数据导入与异常识别功能
```

PR 描述至少需要说明：

1. 本次完成了什么功能；
2. 修改了哪些文件；
3. 如何运行和测试；
4. 测试使用了什么数据；
5. 产生了什么输出结果；
6. 是否存在已知问题；
7. 是否需要项目负责人调整公共接口。

## 7. 合并与验收规则

项目负责人将在 PR 的 `Files changed` 页面进行检查，主要包括：

1. 是否只修改了本人负责的模块目录；
2. 是否误改了框架或其他模块；
3. 是否符合模块接口与交付规范；
4. 是否包含运行说明、依赖说明和测试结果；
5. 是否能在 BambooWorkbench 框架中正常接入；
6. 是否存在异常退出、数据丢失或输出错误。

未经负责人审核，不得自行合并 PR。发现越界修改时，PR 将暂不合并，成员需要先撤回或修正相应改动。

## 8. 分支用途

```text
module/moisture ─────┐
module/boiling ──────┼── PR → integration → 集成测试 → PR → main
module/after-sales ──┘
```

- `main`：稳定、可演示、可安装和可发布的版本；
- `integration`：三个模块的集成与总体测试版本；
- `module/moisture`：原竹丝水分检测模块开发分支；
- `module/boiling`：水煮实验模块开发分支；
- `module/after-sales`：售后分析模块开发分支。

只有项目负责人负责将 `integration` 合并到 `main`。

## 9. 禁止操作

成员不得执行以下操作：

- 不得直接向 `main` 或 `integration` 推送代码；
- 不得进入其他成员的模块分支开发；
- 不得修改其他成员的模块目录；
- 不得自行修改公共接口和框架代码；
- 不得使用 `git push --force` 或 `git push -f`；
- 不得删除远程分支；
- 不得在未经检查时使用 `git add .`；
- 不得自行合并提交到 `main`；
- 不得提交 API 密钥、密码、客户隐私数据或其他敏感信息。

## 10. 出现问题时

如果遇到以下情况，请停止继续操作并联系项目负责人：

- 切换到了错误分支；
- 修改了自己目录以外的文件；
- `git pull` 出现冲突；
- `git push` 被拒绝；
- 需要修改 `contracts/` 或其他公共接口；
- 不确定某个文件应该放在哪里；
- 不确定当前改动是否可以提交；
- 发现仓库中存在敏感信息。

联系负责人时，请同时发送以下命令的输出截图：

```powershell
git branch --show-current
git status
git log -5 --oneline
```

## 11. 重要说明

当前仓库是个人账户下的私有仓库。协作者获得仓库写入权限后，GitHub 不一定能在权限层面严格限制其只能修改某一个目录。因此，所有成员必须遵守本说明中的分支和目录边界。

本项目采用以下控制方式降低误操作风险：

1. 每人固定一个专属开发分支；
2. 每人只提交自己的模块目录；
3. 所有模块统一通过 PR 进入 `integration`；
4. 所有 PR 均由项目负责人审核和合并；
5. `main` 只保存经过总体测试的稳定版本。

请三位成员在开始开发前完整阅读本说明，并确认自己的分支和目录。
