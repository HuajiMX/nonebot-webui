# NoneBot2 WebUI

![最新版本](https://img.shields.io/github/v/release/HuajiMX/nonebot-webui?label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC&color=ea5252)
![Stars](https://img.shields.io/github/stars/HuajiMX/nonebot-webui?label=Stars&color=blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![平台](https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-Windows%20%7C%20Linux%20%7C%20macOS-3a9d7b)
![Release CI](https://img.shields.io/github/actions/workflow/status/HuajiMX/nonebot-webui/release.yml?label=Release%20CI&color=green)
![协议](https://img.shields.io/github/license/HuajiMX/nonebot-webui?label=%E5%8D%8F%E8%AE%AE&color=green)

> 给你的 QQ 机器人一个可视化控制台。

NoneBot2 WebUI 是一个本地网页管理面板，为 [NoneBot2](https://nonebot.dev/) 机器人提供一站式管理：不用记命令、不用碰代码，创建机器人、编写插件、查看日志、打开终端、监控服务器，全部在浏览器里完成。

无论你是想快速搭一个自己的 QQ 机器人，还是想集中管理多个机器人，NoneBot2 WebUI 都能帮你省下大量折腾时间。

## 功能亮点

### 🤖 机器人管理

- 填个表单即可创建机器人，环境与依赖自动安装，开箱即用
- 支持注册已有 NoneBot2 项目：自动识别虚拟环境、按 `pyproject.toml` 同步插件目录，缺失入口时自动生成 `bot.py`
- 一键启动、停止、重启，机器人运行状态一目了然
- 实时运行日志，自动滚动，错误高亮

### 🧩 插件管理

- 上传 `.py` 文件或 `.zip` 插件包即可安装，依赖自动处理
- 随时启用或暂停插件，立即生效

### 🎨 可视化插件编写

- 拖拽节点拼出插件流程，全程无需手写代码
- 多种触发方式：群聊、私信、定时任务、WebHook
- 条件判断、循环遍历、API 请求、自定义代码等组件随心组合
- 发送文本、图片、表情、语音、视频，还能 @ 群友
- 支持多轮对话：信息收集、选项交互，会话数据自动记录
- 一键生成插件并装配到机器人；改完点「更新插件」，即时生效

### 🖥️ 内置终端

- 网页内直接操作机器人环境
- 可配置并打开协议端（如 NapCat）的终端，调试更方便

### 📊 服务器监控

- CPU、内存、磁盘、网络实时图表
- 机器人运行概况与进程情况尽在掌握

### 🔒 账号安全

- 首次启动设置管理员账号，未登录无法访问任何页面
- 所有管理操作都在本地完成，数据由你自己保管

## 快速开始

只需要一台 Windows / Linux / macOS 电脑，并安装 **Python 3.10+**，然后执行一条命令即可完成安装。

**Windows（PowerShell）**

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.ps1 -OutFile install.ps1; .\install.ps1"
```

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.sh -o install.sh && bash install.sh
```

安装完成后：

- **Windows**：进入 `nonebot-webui` 文件夹，双击 `启动WebUI.bat`
- **Linux / macOS**：执行 `cd nonebot-webui && ./.venv/bin/python start.py`

然后打开浏览器访问 `http://127.0.0.1:9527`，按提示设置管理员账号，即可开始使用。

## 快速上手

### 创建第一个机器人

进入「机器人管理」→「创建机器人」，填写名称、选择协议（默认 OneBot V11）和端口，其余交给 WebUI 自动完成。创建好后点击「启动」，就能在日志页实时看到机器人输出。

### 连接你的 QQ

OneBot V11 机器人默认通过反向 WebSocket 工作：在 NapCat 等协议端配置机器人地址（如 `ws://127.0.0.1:18080/onebot/v11/ws`）即可连通。WebUI 的「终端」页还能直接打开协议端终端，方便排查问题。

### 拖出第一个插件

进入「可视化插件编写」，新建插件后：

1. 从左侧拖入一个「触发方式」节点（群聊 / 私信 / WebHook / 定时任务）
2. 再接上「发送消息」等组件，配置好消息内容
3. 保存后点击「装配到机器人」

机器人收到消息就会自动回复。想调整流程？回到编辑器改完点「更新插件」，自动重新装配，无需手动操作。

### 管理插件

在机器人的「插件管理」页上传 `.py` 或 `.zip` 插件包，即可安装使用；暂停或启用插件，点一下立刻生效。

## 版本更新

WebUI 会自动检查新版本。发现更新时，页面顶部会出现提示，点击「立即更新」即可一键升级：自动备份数据、替换程序、重启服务，你的机器人和数据都不会丢失。

## 常见问题

**访问页面提示无法连接？** 确认服务已经启动（Windows 双击 `启动WebUI.bat`），并检查端口是否被占用。

**创建机器人时端口被占用？** 在创建表单里换一个端口即可。

**有建议或遇到问题？** 欢迎在 [GitHub Issues](https://github.com/HuajiMX/nonebot-webui/issues) 反馈。
