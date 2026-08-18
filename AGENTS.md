# AGENTS.md

本文件面向在此仓库中工作的 AI 编码代理，描述项目结构、关键机制与必须遵守的约定。请先通读再动手修改。

## 项目简介

NoneBot2 WebUI 是一个本地 Web 管理面板，用于：

- 创建、启动、停止、监控 NoneBot2 机器人（默认 OneBot V11 协议，也支持 V12 / QQ 官方 / Discord / Telegram / Kook）；
- 查看机器人日志、系统监控、内置终端；
- 通过**可视化流程编辑器**拖拽节点生成 NoneBot 插件（无需手写代码）；
- 自带一键安装脚本与 WebUI 内一键更新（基于 GitHub Releases 发布包）。

仓库地址：`https://github.com/HuajiMX/nonebot-webui`（默认发布源，代码中的 `DEFAULT_UPDATE_REPO` 必须与之保持一致）。

## 技术栈

- 后端：Python 3.10+ / FastAPI / Uvicorn / psutil / WebSocket；依赖见 `requirements.txt`（Python 3.10 解析 `pyproject.toml` 额外依赖 `tomli`，3.11+ 用内置 `tomllib`）
- 前端：Vue 3 / Vite / Element Plus / ECharts / xterm.js / Pinia / Vue Router / axios
- 存储：JSON 文件（`data/` 目录，可用环境变量 `NB_WEBUI_DATA` 覆盖路径）
- 机器人侧：NoneBot2 + OneBot V11（默认），进程由 WebUI 托管
- 界面与代码注释：中文

## 目录结构

```
backend/
  main.py             FastAPI 入口：lifespan 清理孤儿机器人进程、托管构建后的前端、/api/health
  config.py           路径常量（PROJECT_ROOT / DATA_DIR / FRONTEND_DIST）、NB_WEBUI_DATA
  models.py           Pydantic 模型（User / Bot / BotCreate / BotUpdate）
  security.py         密码哈希与 JWT；deps.py 提供 current_user 依赖
  storage.py          JSON 读写工具
  bot_manager.py      机器人注册、脚手架生成（BOT_PY_TEMPLATE）、venv/依赖安装；ADAPTERS 常量
  process_manager.py  机器人子进程生命周期管理
  plugin_manager.py   插件列表、启停、上传安装（.py/.zip）、webui_disabled_plugins.json
  terminal.py         终端会话（pywinpty / ptyprocess）
  monitor.py          系统监控（psutil）
  visual_plugin.py    可视化插件：流程校验、代码生成、NODE_CATALOG 组件目录（权威来源）
  version_check.py    更新检查（30 分钟缓存，update_repo / update_url 可覆盖）
  folder_picker.py    选择系统文件夹
  routers/            auth / bots / plugins / logs / terminal / monitor / visual_plugins / update
frontend/
  src/api/index.js    axios 封装：响应拦截、401 跳登录、wsUrl 自动带 token
  src/router/index.js 路由守卫：/setup、/login 公开，其余需登录
  src/stores/auth.js  Pinia 认证状态
  src/stores/update.js  Pinia 更新状态（版本检查、更新进度轮询；顶栏横幅与设置页共用）
  src/layouts/MainLayout.vue  顶栏（版本更新横幅 + 更新进度对话框，localStorage 记录已忽略版本）
  src/views/          Login / Setup / Dashboard / Bots / BotDetail / VisualPlugins / VisualPluginEditor / Settings
  src/components/     LogPanel / PluginPanel / StatusTag / TerminalPanel
data/                 运行时数据（gitignored，仅保留 .gitkeep，见下方约定）
install.py            一键安装（自动切换到 .venv Python 执行；建 venv、装依赖、建管理员、写配置、生成 启动WebUI.bat）
install.ps1/.sh       一键安装引导脚本（下载发布包 → 解压 → 运行 install.py）
update.py             一键更新脚本（WebUI「立即更新」按钮触发；进度实时写入 data/update.log）
start.py              服务入口（读取 data/config.json 的 host/port，默认 0.0.0.0:9527）
scripts/              Playwright 冒烟测试
.github/workflows/release.yml  打 v* tag 时自动构建前端并发布 nonebot-webui.zip
```

## 常用命令

```powershell
# 启动服务（生产方式）
.\.venv\Scripts\python.exe start.py

# 后端开发热重载
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 9527 --reload

# 构建前端（产物 frontend/dist）
cd frontend; npm install; npm run build

# 冒烟测试（服务已启动、管理员 admin/admin123 时）
.\.venv\Scripts\python.exe scripts\visual_plugin_smoke.py
```

## API 路由一览

| 前缀 | 说明 |
| --- | --- |
| `/api/auth` | 登录、初始化管理员、修改密码 |
| `/api/bots` | 机器人 CRUD、启停、插件列表/启停/上传（plugins、logs 也挂载在同前缀下） |
| `/api/terminal` | 终端（WebSocket，连接需带 token 查询参数） |
| `/api/monitor` | 系统监控数据 |
| `/api/visual-plugins` | 可视化插件 CRUD、`/catalog` 组件目录、安装/卸载到机器人 |
| `/api/update` | `GET /status` 版本检查（`?force=true` 绕过缓存）、`GET /log` 更新进度日志、`POST /` 触发更新 |
| `/api/health` | 健康检查 |

## 核心机制与不变式（重要）

### 数据与路径

- `data/` 是运行时状态：`users.json`、`bots.json`、`config.json`、`visual_plugins.json`、`webui_server.log`、`webui_server.err.log`、`update.log`。
- `data/` 在 `.gitignore` 中（只保留 `data/.gitkeep`）。**绝不把用户数据提交进仓库**；修改代码时不要动本机 `data/` 里的真实数据。
- `data/config.json` 支持 `host`、`port`、`update_repo`、`update_url`、`update_asset` 覆盖项。
- 测试/隔离运行：设置 `NB_WEBUI_DATA` 指向独立目录，端口避开 9527（冒烟测试惯例用 9530）。

### 认证

- 首次使用需初始化管理员（`/setup`，或一键安装时创建）；未登录无法访问任何管理接口。
- 登录态通过 HttpOnly Cookie（`nb_webui_token`）维持，会话保存在后端内存（服务重启后需重新登录）；WebSocket 认证优先取查询参数 `token`（`localStorage.nb_token`），否则用 Cookie。

### 机器人管理

- 机器人由 WebUI 生成 NoneBot2 脚手架并托管进程（`managed=True`），状态机：`creating / starting / running / stopping / stopped / error`。
- 适配器定义在 `bot_manager.ADAPTERS`；创建时选定协议（默认 OneBot V11）。
- `webui_disabled_plugins.json`（机器人目录内）记录被停用的插件，仅托管机器人支持过滤加载。
- 注册已有项目：目录已存在且非空时 `managed=False`，WebUI 自动识别 `.venv`/`venv`/`env` 并解析 Python，不重建脚手架；缺 `bot.py` 时按 `pyproject.toml` 的 `[tool.nonebot]` 自动生成标准入口（适配器兼容 `[tool.nonebot.adapters]` 字典格式与 `adapters = [...]` 列表格式，均取 module_name；未声明时回退注册时选择的协议），已有 `bot.py` 不覆盖；`plugin_dir` 也会按 `[tool.nonebot] plugin_dirs` 的首项自动同步（注册时 + 启动时兜底，仅对 `managed=False` 生效），插件列表/上传目录与实际加载目录保持一致。注册后的入口/目录同步失败不会把状态置为 error（启动时会自动重试）。
- 启动一律以 `[python, bot.py]`（cwd=机器人目录）拉起子进程；启动前兜底检查入口，无法生成时给出明确错误而非「can't open file」。
- **运行判定**：`process_manager.is_running()` 只看 WebUI 自己拉起的子进程（`proc.poll() is None`），WebUI 外部启动的机器人进程不识别；WebUI 重启时 lifespan 会把遗留的 running/stopping 机器人 SIGTERM 并统一置 `stopped`（机器人不会自动恢复）。

### 可视化插件

- **组件目录唯一权威来源是 `backend/visual_plugin.py` 的 `NODE_CATALOG`**；前端通过 `GET /api/visual-plugins/catalog` 获取，改组件必须同步修改 `generate_code()` 的代码生成逻辑。
- 当前分类（前端显示名）：触发方式（群聊/私信监听、WebHook、定时任务）、基本组件（条件判断、循环遍历、自定义代码）、功能（API 请求）、机器人（发送消息）、会话控制（会话入口、信息收集、选项交互、循环结束、会话结束）。
- 配对约束：**循环遍历 ↔ 循环结束**、**会话入口 ↔ 会话结束** 成对出现，自动创建配对节点，左侧用不可删除的线条连接，删除其一则同删。
- 会话按「群号 + QQ 号」创建/复用存储；`session` 变量访问会话内收集的数据；`sender` 仅在消息监听节点下游可用。
- 编辑器的「更新插件」= 保存后自动重新装配到已安装的机器人，不展示生成的 py 代码。
- 生成的文件名为 `vplugin_xxxx.py`，但代码内声明 `PLUGIN_NAME = "真实名称"`；插件列表解析该字段展示显示名（`display_name`），并据模块名前缀标记 `is_visual`（前端显示「可视化」胶囊），启停等操作仍按模块名（`name`）进行。

### 安装 / 更新 / 发布

- **一键安装**：用户执行一条命令（先下载 `install.ps1` / `install.sh` 到本地再执行，**不要改回 `iex (irm ...)` / `curl | bash` 管道执行**）→ 脚本下载 GitHub Releases 的 `nonebot-webui.zip` → 解压 → `install.py` 建 venv、装后端依赖（`frontend/dist` 存在则跳过 npm 构建）、创建管理员、写配置、生成 `启动WebUI.bat`。
- `install.py` 若由系统 Python 启动，会检测 `sys.prefix` 并自动切换到 `.venv` 的 Python 重新执行，避免系统 Python 缺依赖（如 pydantic）导致失败。
- **更新检查**：`version_check.py` 默认访问 GitHub Releases API（`DEFAULT_UPDATE_REPO = "HuajiMX/nonebot-webui"`），30 分钟缓存（`force=true` 绕过）；`data/config.json` 的 `update_url` 优先。
- **一键更新**：WebUI 调 `POST /api/update` → 子进程跑 `update.py`：备份 `data/` → **先下载**新发布包（旧服务仍在运行，前端可实时看进度）→ 停服务 → 校验关键文件（`install.py` / `start.py` / `backend/main.py` / `frontend/dist/index.html`）→ 替换代码（**保留 `data/` 与 `.venv`**）→ `requirements.txt` 哈希变化才重装依赖 → 重启并检测端口（25 秒内未监听则在日志提示手动重启）。Linux/macOS 下更新子进程与新服务均 `start_new_session` 脱离会话，避免被连带结束。
- 更新进度实时写入 `data/update.log`，前端经 `GET /api/update/log` 轮询展示在更新对话框中；完成后提示用户刷新页面。
- **发布新版**：改 `backend/__init__.py` 的 `__version__` → 打 `vX.Y.Z` tag 并推送。GitHub Actions 校验 tag 与版本号一致（不一致构建失败）→ `npm ci` + `npm run build` → 打包代码 + dist 为 `nonebot-webui.zip` → 发布 Release。
- 发布包应始终包含：`backend/`、`frontend/`（含 `dist/`）、`install.py`、`install.ps1`、`install.sh`、`start.py`、`update.py`、`requirements.txt`、`README.md`、`LICENSE`。

## 测试

- `scripts/first_run_test.py`：全新安装首次运行流程（`/setup` → 登录 → 仪表盘）。
- `scripts/ui_smoke_test.py`：前端冒烟（需 9527 端口 + `admin/admin123` + 一个测试机器人）。
- `scripts/visual_plugin_smoke.py`：可视化插件编辑页冒烟（需 9530 端口 + `admin/admin123`，可用本地 http.server 模拟更新源）。
- 修改后端/前端后，先跑相关冒烟测试再交付；测试用隔离数据目录，避免污染真实数据。

## 给开发代理的注意事项

- 搜索用 `rg`；文件编辑用 `apply_patch`；不要用 shell 重定向/`cat` 写文件。
- 环境是 Windows PowerShell，仓库文件为 UTF-8（`install.ps1` 带 BOM，供 Windows PowerShell 5.1 正确显示中文）。PowerShell 内联 Python 传中文易乱码，优先写临时脚本文件或避免中文断言。
- `npm`、`pip`、`git` 写操作、联网、启停服务等命令通常需要提权（escalation）。
- 涉及用户真实数据（`data/`、`E:\Bot\...` 机器人目录）的操作先确认，不擅自删除。
- 修改功能后保持 README 与行为同步；新增/删除组件时同步 `NODE_CATALOG` 与生成逻辑。
- 提交信息遵循 Conventional Commits：格式 `<type>(<scope>): <subject>`，例如 `fix(editor): ...`、`feat(bots): ...`；type 常用 `feat` / `fix` / `docs` / `refactor` / `chore` / `test` / `build` / `perf`，scope 为可选的改动模块。
- 版本发布走「改 `__version__` → tag → push」，不要在代码里写死本机绝对路径（启动脚本用 `%~dp0` 等可移植写法）。
