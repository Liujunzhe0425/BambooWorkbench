# BambooWorkbench GitHub 协作流程

仓库固定为个人账号下的私有仓库 `BambooWorkbench`。

| Owner | Branch | Primary path |
|---|---|---|
| Framework lead | `integration` | `app/`, `core/`, `ui/`, `contracts/` |
| Moisture member | `module/moisture` | `modules/moisture/` |
| Boiling member | `module/boiling` | `modules/boiling/` |
| After-sales member | `module/after-sales` | `modules/after_sales/` |

## 固定规则

1. `main` 只保存可演示、可安装的稳定版本。
2. 框架工作进入 `integration`。
3. 三个模块分支从同一个冻结的 `integration` 提交创建。
4. 组员只能修改自己 `modules/<module_id>/` 路径。
5. 模块 PR 的目标是 `integration`，绝不直接合并到 `main`。
6. PR 必须通过 `quality`、合同验证、模块验收清单和框架负责人评审。
7. 三模块联合验收后，再由 `integration` 向 `main` 发起发布 PR。

## 组员日常命令

```powershell
git switch module/moisture
git pull --ff-only
git status --short
git add modules/moisture
git commit -m "feat(moisture): implement quality workbook processing"
git push origin module/moisture
```

提交前运行模块测试和 `scripts/verify_repo.ps1`。真实数据、输出、日志、数据库、安装包和密钥不得上传。

## 框架负责人接收顺序

1. 在 GitHub 查看 PR 范围和 CI；
2. 下载脱敏验收材料并核对 SHA-256；
3. 在独立工作树运行合同和模块测试；
4. 按模块验收清单核对业务证据；
5. 接入统一桌面流程并回归另外两个模块；
6. 有问题就在 PR 中退回，不在框架核心打补丁掩盖；
7. 满足门槛后合并到 `integration`。

首次私有仓库建仓、分支和成员邀请见 [`GitHub私有仓库建仓与上传教程.md`](GitHub私有仓库建仓与上传教程.md)。
