# BambooWorkbench GitHub 私有仓库建仓与上传教程

> 适用时间：2026-07-13
> 本教程不会自动执行任何远程操作。按照下列步骤人工建立个人账号下的私有仓库。

## 0. 上传前准备

1. 准备你自己和三位组员的 GitHub 用户名；
2. 确认仓库本地路径为 `D:\Project\BambooWorkbench`；
3. `.github\CODEOWNERS` 中的用户名占位符是预期状态，首次上传后按第 5 节通过 PR 统一替换；
4. 不要把企业真实 Excel、日志、数据库、`.env` 或 API 密钥放入项目目录。

GitHub 官方特别建议：将已有本地仓库推送到新建远端仓库时，远端不要预先初始化 README、`.gitignore` 或 License，否则容易产生无关的首次历史冲突。参考 [Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 1. 在网页上创建私有仓库

1. 登录 [GitHub](https://github.com/)；
2. 右上角点 `+` → `New repository`；
3. `Owner` 选你的个人账号；
4. `Repository name` 填 `BambooWorkbench`；
5. `Description` 可填：`竹简工作台——桃花江竹材品质数据本地桌面框架`；
6. 可见性选 **Private**；
7. **不勾选** `Add a README file`、`.gitignore` 和 License；
8. 点 `Create repository`；
9. 在 `Quick setup` 页复制 HTTPS 地址，形如 `https://github.com/<你的账号>/BambooWorkbench.git`。

## 2. 将本地完整框架推送到 GitHub

在 Windows 开始菜单打开 PowerShell，逐行执行：

```powershell
Set-Location -LiteralPath 'D:\Project\BambooWorkbench'
git status --short
git remote -v
git remote add origin https://github.com/<你的账号>/BambooWorkbench.git
git remote -v
git push -u origin main
git push -u origin integration
git push -u origin module/moisture
git push -u origin module/boiling
git push -u origin module/after-sales
```

注意：

- 请将 URL 里的 `<你的账号>` 替换为真实用户名；
- 第一次推送时 Git Credential Manager 可能弹出浏览器登录，按提示授权即可；
- `git status --short` 应无输出。如果出现不认识的数据文件，先停止并检查，不要执行 `git add .`；
- 如果已有名为 `origin` 的地址，不要再添加；先用 `git remote -v` 核对。地址错了可执行 `git remote set-url origin <正确URL>`。

推送已有本地仓库的官方命令流程同样见 [GitHub 官方文档](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 3. 确认远端状态

回到仓库网页，检查：

- 仓库名旁显示 `Private`；
- 默认分支是 `main`；
- 分支列表中存在 `integration`、`module/moisture`、`module/boiling`、`module/after-sales`；
- `Actions` 页的 `quality` 工作流开始运行且最终变绿；
- README 明确显示“v0.1.0 空框架，不包含三类真实业务算法”。

若默认分支不是 `main`：`Settings` → `General` → `Default branch` 中改为 `main`。

## 4. 邀请三位组员

1. 进入仓库 `Settings`；
2. 左侧 `Collaborators` 或 `Collaborators and teams`；
3. 点 `Add people`；
4. 依次搜索三位组员的 GitHub 用户名并发出邀请；
5. 等对方接受邮件/站内邀请。

GitHub 个人私有仓库的协作者可读取和推送代码；个人账号仓库不支持给单个协作者更细的只读/路径级权限。参考 [Inviting collaborators to a personal repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository) 和 [Permission levels for a personal account repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)。

## 5. 替换 CODEOWNERS 占位符

邀请发出后，修改 `.github/CODEOWNERS`，将四个占位账号替换为真实用户名：

```text
@OWNER_GITHUB_USERNAME
@MOISTURE_GITHUB_USERNAME
@BOILING_GITHUB_USERNAME
@AFTER_SALES_GITHUB_USERNAME
```

为了不打乱本地 worktree 和已分配的模块分支，推荐在 GitHub 网页上完成这个单独变更：

1. 将网页左上分支切到 `integration`；
2. 打开 `.github/CODEOWNERS`，点铅笔编辑；
3. 替换全部四个占位符；
4. 提交时选择创建新分支，命名 `chore/configure-codeowners`；
5. 创建目标为 `integration` 的 Pull Request；
6. 检查只改了 CODEOWNERS，等 `quality` 通过后合并。

该变更会在下一次 `integration` 发布到 `main` 时同步进入主分支。在 CODEOWNERS 尚未生效的这一个 PR 上，由框架负责人手动审查。

## 6. 分支保护：先看你的 GitHub 套餐

GitHub 当前官方规则是：公开仓库可在 GitHub Free 使用 rulesets/保护分支；**私有仓库需要 GitHub Pro、Team 或 Enterprise**。参考 [Creating rulesets for a repository](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository) 与 [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。

### 如果你的私有仓库支持 Rulesets

进入 `Settings` → `Rules` → `Rulesets` → `New branch ruleset`：

1. 创建 `protect-main`，目标分支为 `main`；
2. Enforcement 设为 `Active`；
3. 开启 `Require a pull request before merging`；
4. 审核数设为 1，开启新提交后旧审核失效；
5. 开启 `Require status checks to pass`，等 Actions 至少运行一次后选择 `quality`；
6. 开启必须解决对话、阻止 force push 和阻止删除；
7. 对 `integration` 创建类似规则，保留 PR、`quality` 和对话解决要求。

必须状态检查的原理与可用规则见 [Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)。

### 如果你是 GitHub Free 个人私有仓库

页面可能不提供可执行的分支保护。这不是操作错误。可选方案：

- 保持私有 + 免费：通过团队约定禁止直推 `main/integration`，只合并 PR，由你人工检查 Actions；
- 需要强制保护：升级 GitHub Pro，再按上述规则配置；
- 不要为获得 Free 保护而把企业项目改为公开仓库。

## 7. 发给三位组员的首次操作

三位组员接受邀请后，各自执行对应分支。以水分模块为例：

```powershell
git clone https://github.com/<你的账号>/BambooWorkbench.git
Set-Location -LiteralPath '.\BambooWorkbench'
git switch module/moisture
git pull --ff-only origin module/moisture
```

然后严格按 [`三个业务模块最终交接说明.md`](三个业务模块最终交接说明.md) 在本人 `modules/<module_id>/` 中开发。

## 8. 常见问题

### `remote origin already exists`

```powershell
git remote -v
git remote set-url origin https://github.com/<你的账号>/BambooWorkbench.git
```

### 第一次 push 出现 `rejected (fetch first)`

通常是建仓时误勾选了 README/License。不要 force push。最简单做法是删除还没有人使用的新远程仓库，按第 1 节重新创建空仓库；如果远端已有需要保留的工作，先停止并单独处理历史合并。

### 找不到 `quality` 必须检查

先推送一次 `integration` 或创建一个 PR，等 `.github/workflows/quality.yml` 成功运行后再进入 Rulesets 选择。

### 上传后才发现有密钥或真实数据

立即把仓库保持为私有，撤销/更换密钥，并停止继续推送。仅删除最新文件不会从 Git 历史中消失，需另行清理历史。

## 9. 完成标准

当以下项全部成立，手动建仓完成：

- [ ] 仓库名为 `BambooWorkbench` 且显示 `Private`；
- [ ] 五个本地分支已推送；
- [ ] 默认分支为 `main`；
- [ ] `quality` Actions 已经通过；
- [ ] CODEOWNERS 中没有未替换的用户名占位符；
- [ ] 三位组员已接受邀请；
- [ ] 三人都能切换到各自 `module/*` 分支；
- [ ] 已根据套餐配置强制保护，或明确采用免费私有仓库的人工 PR 约定；
- [ ] 仓库中没有真实企业数据、日志、数据库或密钥。
