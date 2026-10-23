# Windows 完整离线包与依赖分支

2026-10-23。用户要求在 fork 单独开分支，下载解压后通过 `MARS-Windows.cmd` 使用，依赖随包提供。

| 问题／优化点 | 原因与确定方案 | 修改结果与验证 |
| --- | --- | --- |
| 完整离线交付与打包完整性 | GitHub main 的约 7MB 源码 ZIP 不含依赖；旧发行白名单还漏了当前 Coding/ZCode 必需模块。补齐 16 个文件并增加全部已跟踪后端 Python 模块的覆盖检查；完整包携带 Windows 工具、Python wheels、npm 缓存和 ZCode。大文件以普通 Git 二进制分片交付，启动时用流式 IO 自动合并并验证，不依赖 Git LFS。 | Windows 实机 CI 离线首次安装、真实 CPU 作业/子进程/停止、前端和项目接口、ZCode 握手、重复启动、两次核心更新均通过；更新保留依赖、配置及用户文件。分支与 Release 已实际发布，并核对公共 GitHub 清单、真实二进制大小和 Release SHA256。 |

## 已发布内容

- 用户分支：[windows-offline](https://github.com/stran0003/MARS-Multi-Agent-Research-System/tree/windows-offline)，提交 `f079815bc3c6716dd7198f5b8e3593b9db756c38`。
- [完整离线包](https://github.com/stran0003/MARS-Multi-Agent-Research-System/releases/download/windows-offline-20261023/MARS-Product-Windows-Offline.zip)：659,828,919 字节，约 660MB。
- [同版核心更新包](https://github.com/stran0003/MARS-Multi-Agent-Research-System/releases/download/windows-offline-20261023/MARS-Core-Update.zip)：2,651,319 字节；配置中的默认更新地址指向本 fork 的最新 Release。
- 构建源码位于 `codex/windows-offline-20261023`，验收使用源码提交 `94c57d2a628b1ecf4c97a701643b94cd04b274dc`。未修改 main，未推送原作者仓库，未停止用户本机 MARS。

完整包 SHA256：`88d99c6aa9c45462c46fd3c50459d3c814982e286d864bcfee6e067a69f9885b`，已与 Release 的 digest 及公开下载的 SHA256SUMS.txt 比对。依赖包含 166 个 Windows wheels、553 个 Windows npm 包缓存及工具，共 175 个逻辑依赖文件。分支实际依赖字节约 666MB，单个 Git blob 最大 48MiB；`.gitattributes` 禁止字节转换，无 LFS 指针。

## 验证边界与用法

[Windows CI 39946862614](https://github.com/stran0003/MARS-Multi-Agent-Research-System/actions/runs/39946862614) 的构建、离线验收和发布均成功。验收显式设置 `UV_OFFLINE`、禁止 Python 下载、npm 离线模式及不可用的外部代理，真实安装和启动带分片的分发目录。确认前端确实提供更新后的代码，再恢复原始代码；没有模型请求或真实研究训练，不将安装验收称为科学性能验证。

本机还完成 54 项相关检查，1 项因 Windows 符号链接权限跳过；新增 Python 严格类型检查、PowerShell 5.1 语法/配置检查、仅使用导出源码的真实后端导入通过。CI 回执和公开发布核对记录保存在仓库外 `outputs/mars-maintenance-01a12379/offline-verification-39946862614/`。

下载完整包，解压并进入 `MARS-Product`，双击 `MARS-Windows.cmd`。首次使用包内缓存本地安装并构建前端，之后复用运行环境。也可以下载 windows-offline 分支 ZIP；较大依赖由同一个入口自动合并。首次使用仍需配置自己的模型 API，并接入自己的研究代码和数据；包中不含用户凭据或研究资料。
