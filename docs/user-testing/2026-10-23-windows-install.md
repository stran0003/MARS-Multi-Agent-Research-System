# Windows 一键安装与当前版发布验收

2026-10-23，Windows 10 x64 实机。用户选择将当前整版发布到自己的 fork main，保留旧 main 提交历史；未推送原作者仓库。

| 问题／优化点 | 原因与修改结果 | 验证与边界 |
| --- | --- | --- |
| 一键安装遗漏 ZCode | 恢复旧 main 的官方运行组件安装实现，适配 `dependencies/windows` 与旧 `local/windows`；安装和启动均进行真实 app-server 握手，缺失时单独修复。明确配置的 command 保留优先权；离线包仍只使用包内组件。 | 干净 Git 下载副本实际安装 ZCode 3.15.1；移走运行目录后 CMD 启动自动恢复，Python/npm 安装收据时间未变。未调用模型。 |
| CMD 从 PowerShell 7 启动时模块冲突 | Windows PowerShell 继承了 PowerShell 7 的模块路径，下载后 `Get-FileHash` 不可用；7 个原生 CMD 入口在局部环境重建模块搜索路径。修正 README 中旧 Docker 入口、API 配置步骤和超时说明；CI 覆盖 CMD 安装及重启。 | 从 PowerShell 7 经真实 CMD → Windows PowerShell 5.1 安装、启动、停止、重启均成功；不修改系统环境变量。 |

## 实机过程

- 从 GitHub 克隆 `stran0003/MARS-Multi-Agent-Research-System` 的当前开发分支，再应用本次安装修复，代码运行文件与发布版本逐文件核对相同。
- 独立目录 `MARS-install-check-20261023`，端口 3301/8810。未复制 `.env.local`、项目、数据或已安装的虚拟环境；原 3001/8010 服务未重启，验证后仍健康。
- 运行真实 `install-mars-windows.cmd`：下载并安装独立 Python 3.11.14、uv、Node、MinGit；新建虚拟环境，安装 165 个 Python 包及 558 个前端包。官方压缩包和 uv/npm 缓存有复用，故不声称所有包均重新从网络下载。下载校验、依赖兼容检查、CPU PyTorch/科学计算/后端导入、ZCode 握手、TypeScript 检查均通过。
- 运行真实 `MARS-Windows.cmd -NoBrowser -SkipConfigure`：设置页面、后端健康、前端版本代理、前端项目接口均返回 200。再次运行复用原进程与依赖收据。
- 真实停止后两个测试端口关闭；保留备份并移走测试副本的 ZCode，再启动自动恢复组件，服务 PID 更新、项目接口正常，依赖收据未改；最后停止测试副本。
- 使用新安装的 Python 环境运行安装、ZCode 发现、核心更新和打包相关测试：**96 通过、1 跳过、0 失败**。跳过项需要 Windows 文件符号链接权限。相关 Python 严格类型检查、PowerShell 5.1/7 脚本检查通过。

本地证据保存在仓库外 `outputs/mars-maintenance-01a12379/windows-install-check-20261023.json`；回归 XML 为 `runs/windows-install-final.xml`，测试服务日志为测试副本的 `local/windows/logs/`，均未随源码发布。过程中发现的首次模块错误和 Windows 路径大小写测试误报已修复后重验。

本次验收针对安装及服务生命周期，不等于运行了完整模型研究或验证科学性能；模型请求、训练次数均为 0。其他电脑需能访问安装源，研究前在设置页配置自己的模型 API，再接入自己的代码与数据。离线发行包没有重新构建，已有离线组件发现与更新兼容测试通过。
