# YysScript — 阴阳师自动化脚本工作区

本仓库是我自用的《阴阳师》挂机脚本工作区，基于开源项目
[runhey/OnmyojiAutoScript](https://github.com/runhey/OnmyojiAutoScript) 修改而来，
外加一个 Flutter 写的图形启动器 `OASX`。

## 目录结构

```
YysScript/
├─ OnmyojiAutoScript/     # 脚本主体（Python，来自上游 OAS，含本地定制）
│  ├─ tasks/              # 各功能任务实现，大量游戏界面模板图
│  ├─ module/             # 设备控制、配置、UI 等基础模块
│  ├─ fluentui/           # 内嵌的 FluentUI 组件
│  └─ config/             # 配置目录（个人账号配置不入库）
├─ OASX/                  # Flutter 图形启动器（已编译产物）
├─ _find-conda.bat        # 自动定位本机 conda（被下面几个脚本调用）
├─ launch-oas.bat         # 一键启动（推荐入口）
├─ launch-oas.ps1
├─ start-oas.bat          # 只启后端，日志打在窗口里
├─ install-deps.bat       # 一次性装环境：建 .conda + 装依赖
├─ 部署指南.md            # 换电脑怎么从零跑起来
└─ 使用说明.md            # 本地定制功能的详细笔记
```

## 运行

> 换电脑 / 第一次使用，请看 **[部署指南.md](部署指南.md)**，里面有从零安装的完整步骤。

1. 首次使用先跑 `install-deps.bat`：自动创建 Python 3.10 环境并安装依赖。
2. 先启动模拟器（分辨率必须是 **1280×720**），再双击 `launch-oas.bat` 启动，或直接运行 `OASX/oasx.exe`。
3. OASX 登录页 Address 填 `127.0.0.1:22267`（不要加 `http://`），用户名密码留空。
4. 后端服务默认监听 `http://127.0.0.1:22267`。

脚本会自动在本机查找 conda；装在非常规位置时，在项目根目录建一个 `conda-path.txt` 写一行 conda.bat 的完整路径即可。

## 相对上游的本地改动

- **悬赏封印（WantedQuests）**：适配 2026-10 游戏界面改版
  - 面板由竖排列表改为横向卡片，重做「一键追踪 / 取消追踪」模板与搜索区域
  - 详情页四行布局与「前往」按钮重做模板，OCR 区域同步调整
  - 新增「领取」已完成奖励
  - 详情页打开判断改为「出现前往按钮」，修复连点导致的 `GameTooManyClick`
  - 新增「点击屏幕继续」结算页处理，避免 `GameStuckError`
- 以及若干任务、设备连接、服务端的本地修补（详见提交记录）

## 说明

- 仓库不包含：Python 运行环境（`.conda`）、运行日志、截图、自动生成的配置备份。
- 游戏界面模板图（`tasks/**/*.png`）是脚本识别界面的依赖，属于必要资源。
- 本项目仅供个人学习与技术研究使用，请遵守游戏用户协议。
