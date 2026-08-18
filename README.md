# NoneBot2 WebUI

为 [NoneBot2](https://nonebot.dev/) 提供的网页管理面板，支持机器人创建与管理、插件启停与安装、实时日志、内置终端与服务器监控，降低机器人运维成本。

## 功能特性

### 机器人管理
- 创建机器人：填写名称、目录、协议/适配器、端口等，自动创建虚拟环境并安装 NoneBot2 与对应适配器
- 暂停、重启、删除机器人（删除时可选择同时移除目录）
- 修改机器人信息（名称、端口、插件目录、协议端终端命令等）与 `.env` 配置
- 实时展示机器人运行日志（终端输出），支持自动滚动与错误高亮
- 支持直接采用已存在的 NoneBot2 项目目录（不重建脚手架）

### 插件管理
- 每个机器人独立管理插件
- 查看插件列表与启用/暂停状态
- 安装插件：支持单个 `.py` 文件或 `.zip` 包（源码插件自动解压到插件目录；含 `pyproject.toml`/`setup.py` 的包自动 pip 安装；自动处理 `requirements.txt` 依赖）
- 切换启用/暂停后自动重启机器人生效（NoneBot2 5.x 与旧版本兼容）

### 可视化插件编写
- 拖拽组件拼装机器人流程：触发方式（群聊/私信/WebHook/定时任务）、条件判断（多条件且/或/取反）、循环遍历（自动配对循环结束）、API请求（HTTP 调用，响应存入变量）、自定义 Python 代码块、发送消息等
- 消息内容支持文本、图片、QQ 内置表情、表情包、艾特、语音、视频
- 会话控制：会话入口（会话存储管理，自动配对会话结束）、信息收集（等待用户回复后继续流程，收集结果存入会话）
- 一键生成 OneBot 通用协议（V11）NoneBot 插件 `.py` 并装配到机器人；编辑后点「更新插件」可自动重新装配到所有已装配的机器人
- 编辑器底部展示当前可用变量（悬浮查看含义），可拖拽或双击插入条件、消息等内容；节点端口可拖拽连线，连线可点选删除
- 无限画布支持拖拽平移与缩放（50%~150%）
- 流程中可用 `{{变量}}` 引用消息内容、发送人、系统信息、会话回复等

### 内置终端
- 进入每个机器人自带虚拟环境的终端
- 协议端终端：可配置 NapCat 等协议端命令直接打开
- 支持自定义命令终端
- Windows 使用 ConPTY/WinPTY，Unix 使用 pty

### 服务器监控
- 实时展示 CPU、内存、磁盘占用与网络吞吐
- 近 2 分钟趋势图、Top 进程、机器人运行概况

### 身份认证
- 登录系统，未登录用户无法访问任何管理接口与页面
- 首次使用需初始化管理员账号（一键安装时设置，或 WebUI 首次启动时设置）
- 支持修改密码

## 技术栈

- 后端：Python 3.10+ / FastAPI / Uvicorn / psutil / WebSocket
- 前端：Vue 3 / Vite / Element Plus / ECharts / xterm.js
- 存储：JSON 文件（`data/` 目录，可通过环境变量 `NB_WEBUI_DATA` 覆盖）
- 主题色：`#ea5252`（橙）/ `#f2f2f2`（灰）/ 白色

## 一键安装

### 前置要求

- 用户安装：只需 Python 3.10+（发布包已内置构建好的前端页面，无需 Node.js）
- 源码开发：另需 Node.js 18+ 与 npm（重新构建前端时使用）

### 一键安装脚本（推荐）

发布后，未安装用户只需执行一条命令，脚本会自动完成：下载发布包 → 解压 → 安装 Python 依赖 → 设置管理员账号 → 生成启动脚本（命令会先把脚本下载到本地文件再执行，方便查看）：

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.ps1 -OutFile install.ps1; .\install.ps1"
```

Linux / macOS：

```bash
curl -fsSL https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.sh -o install.sh && bash install.sh
```

如需先下载脚本查看内容再执行，也可以分两步：

```powershell
powershell -Command "Invoke-WebRequest -Uri https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.ps1 -OutFile install.ps1"
powershell -ExecutionPolicy Bypass -File install.ps1
```

```bash
curl -fsSL https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.sh -o install.sh
bash install.sh
```

脚本默认使用 `HuajiMX/nonebot-webui` 仓库的 GitHub Releases 发布包；如需覆盖，Windows 可加 `-Repo owner/repo` 参数，Linux / macOS 可用 `bash install.sh owner/repo`。

安装完成后：

- Windows：进入 `nonebot-webui` 目录，双击 `启动WebUI.bat`
- Linux / macOS：`cd nonebot-webui && ./.venv/bin/python start.py`
- 浏览器访问 `http://127.0.0.1:9527`

### 手动安装（源码）

### Windows

```bat
python install.py
```

脚本会依次：
1. 在项目根目录创建 `.venv` 虚拟环境并安装后端依赖
2. 安装前端依赖并构建页面
3. 提示设置管理员用户名与密码（也可用 `--username` / `--password` 参数）
4. 生成 `启动WebUI.bat` 启动脚本

安装完成后双击 `启动WebUI.bat`，或运行：

```bat
.venv\Scripts\python.exe start.py
```

浏览器访问 `http://127.0.0.1:9527`。

### Linux / macOS

```bash
python3 install.py
python3 start.py
```

（手动安装时，若 `frontend/dist` 已存在会自动跳过前端构建；需要重新构建时加 `--force-build-frontend`。）

### 常用参数

```bash
python install.py --username admin --password 123456     # 指定账号密码
python install.py --port 8080                            # 修改监听端口
python install.py --skip-frontend                        # 跳过前端构建（仅更新后端）
python install.py --force-build-frontend                 # 强制重新构建前端
python install.py --start                                # 安装完成后直接启动
```

## 版本更新

WebUI 启动时会自动向发布源检查新版本，发现新版后页面顶部显示更新横幅，点击「立即更新」即可一键升级（自动备份 `data/` → 替换代码 → 依赖变化则重装 → 重启服务），数据不丢失。

发布源默认值写在 `backend/version_check.py` 的 `DEFAULT_UPDATE_REPO`（发布前改成你的仓库 `owner/repo`，随代码分发，所有用户自动生效）；也可在 `data/config.json` 中覆盖（`data/` 不会随仓库推送，仅对本机生效）：

```json
{
  "update_repo": "owner/repo",
  "update_url": "",
  "update_asset": "nonebot-webui.zip"
}
```

- `update_repo`：GitHub 仓库 `owner/repo`，从 Releases 最新版检查
- `update_url`：自定义 JSON 地址（返回 `{"version": "1.1.0", "download_url": "...", "notes": "..."}`），可指向 Gitee/OSS 等镜像
- `update_asset`：发布包文件名，默认 `nonebot-webui.zip`

## 发布新版本（开发者）

1. 修改 `backend/__init__.py` 中的 `__version__`
2. 推送代码并打 tag：`git tag vX.Y.Z && git push origin vX.Y.Z`
3. GitHub Actions 自动执行：校验版本号一致 → 构建前端 → 打包（代码 + 前端 dist）→ 创建 Release 并上传 `nonebot-webui.zip`

## 使用说明

### 创建机器人

1. 进入「机器人管理」→「创建机器人」
2. 填写名称、目录（不存在会自动创建）、协议/适配器（OneBot V11 / OneBot V12 / QQ / Discord 等）、端口
3. 创建过程实时显示进度（虚拟环境 → 依赖安装 → 文件生成）
4. 创建完成后即可启动机器人，日志将实时展示在「运行日志」页

### 接入 NapCat 等协议端

OneBot V11 机器人默认以反向 WebSocket 方式工作：

1. 机器人监听 `HOST:PORT`（如 `127.0.0.1:18080`）
2. 在 NapCat 中配置 WebSocket 客户端地址：`ws://127.0.0.1:18080/onebot/v11/ws`
3. 在机器人「概览」页的「协议端终端命令」中填写 NapCat 可执行文件路径（如 `napcat` 或 `D:\napcat\napcat.exe`），即可在「终端」页打开协议端终端

### 插件安装

- `.py` 文件：在「插件管理」页上传，自动校验语法并放入插件目录
- `.zip` 包：支持三种形式
  - 单文件/插件包源码：解压到插件目录
  - 带 `pyproject.toml` / `setup.py`：自动 `pip install` 到机器人虚拟环境
  - 含 `requirements.txt`：自动安装依赖
- 启用/暂停插件会写入 `webui_disabled_plugins.json` 并在重启后生效（WebUI 会自动重启）

### 可视化插件编写

1. 进入左侧边栏「可视化插件编写」→「新建插件」，创建后进入流程编辑器
2. 从左侧组件面板拖入「触发方式」（群聊 / 私信 / WebHook / 定时任务）作为流程入口，再依次拖入其它组件；双击组件也可快速添加
3. 条件判断节点拥有「成立 / 不成立」两个出口；循环遍历、会话入口会自动生成配对的「循环结束」「会话结束」节点（左侧虚线连接，同生共死，删除其一两者皆删）
4. 点击画布中的节点，在右侧面板配置参数；节点底部的端口可拖拽到其它节点的输入端口连线，也可在「流程连接」中修改，选中连线后可删除
5. 点击「保存」保存流程；首次使用在插件列表页选择「装配到机器人」，之后在编辑器中点「更新插件」即可把最新流程自动重新装配到所有已装配的机器人（运行中会自动重启生效）
6. 生成的插件会出现在机器人「插件管理」中，可随时启用/暂停；在可视化插件列表也可卸载或删除

可用变量（`{{变量名}}` 引用，自定义代码块中可直接使用）：

- `msg`：监听到的消息文本；`raw_msg`：原始消息；`segments`：消息段列表（如 `{{segments.0.type}}`）
- `user_id` / `group_id`：发送人 QQ 号 / 群号；`sender`：发送人信息（`{{sender.nickname}}`）；以上消息相关变量仅在群聊/私信监听分支可用
- `reply`：会话中用户最近一次回复；`webhook`：WebHook 请求负载（可在 WebHook 节点配置「保存到变量」自定义变量名，JSON/表单/纯文本均支持）
- `system`：系统信息（`{{system.cpu}}`、`{{system.memory}}`、`{{system.gpu}}` 等）
- `bot_id` / `bot_name`：机器人自身信息；`event` / `bot`：NoneBot 原生事件与机器人对象

API请求节点的响应会存入配置的变量（默认 `api_resp`），包含 `status`（状态码）、`data`（解析后的 JSON）、`text`（原文）、`headers`（响应头），可用 `{{api_resp.status}}`、`{{api_resp.data.xxx}}` 引用。

### 配置文件

机器人详情「配置文件」页可直接编辑 `.env`（HOST / PORT / DRIVER / SUPERUSERS 等），保存后重启生效。WebUI 生成的 `bot.py` 内置插件过滤加载逻辑，同时兼容 NoneBot2 2.x/3.x/5.x。

## 开发

### 目录结构

```
backend/          FastAPI 后端
  routers/        API 与 WebSocket 路由
  bot_manager.py  机器人注册、创建脚手架、配置
  process_manager.py  进程与日志管理
  plugin_manager.py   插件列表/启停/安装
  visual_plugin.py    可视化插件存储与代码生成
  terminal.py     终端会话（ConPTY/WinPTY/pty）
  monitor.py      系统监控
frontend/         Vue 3 前端（Vite）
  src/views/      页面
  src/components/ 组件
scripts/          Playwright UI 冒烟测试
install.py        一键安装脚本
start.py          启动脚本
data/             运行数据（用户、机器人注册信息、日志）
```

### 本地开发

```bash
# 终端 1：后端（热重载）
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 9527

# 终端 2：前端开发服务器（代理到 9527）
cd frontend
npm run dev
```

访问 `http://127.0.0.1:5173`。

### API 概览

认证接口：`/api/auth/status` `setup` `login` `logout` `me` `password`

机器人接口：`/api/bots`（增删改查）、`/api/bots/{id}/start|stop|restart`、`/api/bots/{id}/config`

插件接口：`/api/bots/{id}/plugins`、`/api/bots/{id}/plugins/{name}/enabled`、`/api/bots/{id}/plugins/upload`

可视化插件接口：`/api/visual-plugins`（增删改查）、`/api/visual-plugins/{id}/generate|install|uninstall`、`/api/visual-plugins/catalog`

实时接口（WebSocket）：
- `/api/bots/{id}/log/ws` — 机器人实时日志
- `/api/terminal/ws?bot_id=xxx&type=bot|protocol|custom` — 内置终端
- `/api/monitor/ws` — 服务器监控

## 安全说明

- 会话使用服务端随机令牌 + HttpOnly Cookie，7 天有效
- 密码使用 PBKDF2-HMAC-SHA256（12 万次迭代）加盐存储
- 插件上传做了语法校验与 zip 路径穿越防护
- 删除机器人目录时禁止删除盘符根目录

## 常见问题

**机器人启动报 `ModuleNotFoundError`**：创建机器人时会自动安装对应适配器；若为已存在的旧项目，请确认其虚拟环境中依赖完整。

**端口被占用**：修改机器人「概览」页的监听端口，或检查是否有残留进程。

**前端页面无法打开**：确认执行过 `python install.py` 完成前端构建，或检查 `frontend/dist` 是否存在。
