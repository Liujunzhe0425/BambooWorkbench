# BambooWorkbench 自动更新设计与发布约定

## 用户流程

Windows 安装版启动约 1.5 秒后异步检查最新正式 Release。无更新时不打扰用户；
发现新版本时显示当前版本和目标版本，由用户决定是否下载。用户同意后：

1. 从独立公开二进制仓库的受信任 GitHub Release 地址下载安装包；
2. 按 Release 元数据中的 SHA-256 校验完整性；
3. 校验通过后启动隐藏的系统更新辅助进程；
4. 竹简工作台正常退出，Inno Setup 覆盖安装；
5. 安装完成后重新启动竹简工作台。

更新检查、下载或安装失败不会阻止三个离线业务模块继续使用。本地数据位于安装根目录，
覆盖安装不会删除 source、output、任务、设置、知识或历史结果。

源码运行默认不自动检查更新，避免开发测试误覆盖已安装版本。可在系统设置中手动检查；
如确需测试源码检查流程，可设置 `BAMBOO_ENABLE_SOURCE_UPDATE_CHECK=1`。

## 安全边界

- 只接受 HTTPS 和固定 GitHub 下载域名；
- 安装包文件名必须与 Release 语义版本完全一致；
- 必须存在 GitHub 提供的 `sha256:` digest，大小和哈希不一致时拒绝安装；
- 客户端匿名访问公开二进制源，不读取或发送 GitHub 访问令牌；
- 更新必须由用户确认，应用不会在后台静默安装；
- 更新器只替换程序目录，不迁移或删除本地业务数据。

后续面向企业大范围部署时，建议再为安装包和主程序配置 Windows Authenticode 代码签名。

## 私有源码与公开二进制隔离

`Liujunzhe0425/BambooWorkbench` 继续作为私有源码仓库；自动更新固定读取公开仓库
`Liujunzhe0425/BambooWorkbench-Distribution`。公开仓库只包含安装包、便携包、摘要和
版本说明，不包含源码与业务数据。客户端不再需要 Token，旧版本保存过的
`github-updates` 凭据也不会被读取，可由用户在系统设置中删除。

完整发布约定见[公开二进制更新源](public-binary-distribution.md)。

## 每次正式发布必须验证

1. 安装包命名为 `BambooWorkbench-Setup-x.y.z.exe`，与标签 `vx.y.z` 一致；
2. Release 是正式发布，不是 Draft 或 Pre-release；
3. Release API 的安装包资产包含 SHA-256 digest；
4. 从上一正式安装版启动，能够提示、下载、校验、退出安装并重启；
5. 拒绝更新、断网、私有源无权限、错误哈希和下载中断时，离线业务仍可使用；
6. 未配置任何 GitHub Token 时仍能发现并下载公开更新；
7. 覆盖更新后本地任务、设置、API Key、知识库和历史结果仍保留。
