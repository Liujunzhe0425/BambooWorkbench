# 公开二进制更新源

BambooWorkbench 源码仓库保持私有。普通客户的自动更新只访问公开仓库
`Liujunzhe0425/BambooWorkbench-Distribution`，该仓库不得包含源码、客户数据、任务、
日志、数据库、API Key 或 GitHub Token。

## 发布内容

每个正式版本只发布三项资产：

- `BambooWorkbench-Setup-x.y.z.exe`
- `BambooWorkbench-Portable-x.y.z.zip`
- `SHA256SUMS.txt`

客户端匿名读取公开仓库的 `releases/latest`，要求正式 Release、版本匹配的安装包、
GitHub `sha256:` digest、可信 HTTPS 下载域名和不超过 500 MiB 的资产。下载后再次在本机
计算 SHA-256，校验通过且用户确认后才覆盖安装。

## 发布步骤

1. 在私有源码仓库完成 PR、完整测试、`integration → main` 和正式标签。
2. 从标签对应提交运行 `build_installer.ps1`、`verify_installer.ps1` 和
   `prepare_release.ps1`。
3. 先将相同资产发布到私有源码 Release，保留开发审计记录。
4. 运行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish_public_release.ps1 -Version x.y.z
   ```

5. 使用无认证 HTTP 请求复验公开 `releases/latest`、资产数量、大小和 digest。
6. 从上一安装版执行一次发现更新、用户确认、下载、校验、覆盖安装和重启测试。

发布脚本只使用发布人员当前的 GitHub CLI 登录会话，不生成、不保存也不打包任何 Token。
若公开分发仓库不存在、被改为私有、资产摘要不匹配或 Release 已存在，脚本必须停止。

## 首次切换说明

v1.3.1 及更早版本仍指向私有源码 Release，因此无法在无令牌环境中发现 v1.3.2。
用户需要最后一次手动安装 v1.3.2；从 v1.3.2 开始，后续正式版本可通过公开源匿名检测更新。
