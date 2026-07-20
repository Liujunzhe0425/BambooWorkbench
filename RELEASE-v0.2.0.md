# 竹简工作台 BambooWorkbench v0.2.0

竹材制造企业品质部数据处理智能工作台。湖南桃花江竹材科技股份有限公司 × 湖大智竹实践团队。

## 版本说明

v0.2.0 为初版正式发布，集成三个业务模块：

| 模块 | 功能 | 文档 |
|---|---|---|
| 竹丝水分检测 | 读取历史水分检测 Excel，自动统计均值、识别异常（标红/标黄），生成分析报告 | modules/moisture/README.md |
| 水煮实验 | 解析水煮实验数据，判定密度/膨胀/剥离，生成统计摘要及复核提示 | modules/boiling/README.md |
| 售后分析 | 提取售后案件信息，按性能/外观/加工多标签分类，生成费用分析与图表 | modules/after_sales/README.md |

## 安装

1. 下载 BambooWorkbench-Setup.exe 安装程序
2. 运行安装，按向导完成（所有文件保存在本地，无需联网）
3. 安装完成后桌面出现快捷方式

## 使用

1. 启动竹简工作台
2. 选择对应的业务模块
3. 导入 Excel 数据文件
4. 点击"开始分析"，等待处理完成
5. 查看生成的 Excel 报告和 Markdown 分析文档

## 技术栈

- Python 3.12 + PySide6
- PyInstaller 便携打包
- 三模块独立运行时，无需安装 Python

## 相关链接

- 仓库：https://github.com/Liujunzhe0425/BambooWorkbench
- 对接企业：湖南桃花江竹材科技股份有限公司
- 团队：湖大智竹实践团队
