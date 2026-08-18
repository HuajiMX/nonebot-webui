"""机器人注册、创建（脚手架/虚拟环境/依赖安装）与配置管理。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 使用 tomli 作为替代
    import tomli as tomllib

from . import config
from .models import Bot, BotCreate
from .storage import load_json, save_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# 支持的协议/适配器
ADAPTERS: Dict[str, dict] = {
    "onebot_v11": {
        "label": "OneBot V11",
        "package": "nonebot-adapter-onebot",
        "import_line": "from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter",
        "register": "driver.register_adapter(OneBotV11Adapter)",
    },
    "onebot_v12": {
        "label": "OneBot V12",
        "package": "nonebot-adapter-onebot",
        "import_line": "from nonebot.adapters.onebot.v12 import Adapter as OneBotV12Adapter",
        "register": "driver.register_adapter(OneBotV12Adapter)",
    },
    "qq": {
        "label": "QQ 官方接口",
        "package": "nonebot-adapter-qq",
        "import_line": "from nonebot.adapters.qq import Adapter as QQAdapter",
        "register": "driver.register_adapter(QQAdapter)",
    },
    "discord": {
        "label": "Discord",
        "package": "nonebot-adapter-discord",
        "import_line": "from nonebot.adapters.discord import Adapter as DiscordAdapter",
        "register": "driver.register_adapter(DiscordAdapter)",
    },
    "telegram": {
        "label": "Telegram",
        "package": "nonebot-adapter-telegram",
        "import_line": "from nonebot.adapters.telegram import Adapter as TelegramAdapter",
        "register": "driver.register_adapter(TelegramAdapter)",
    },
    "kaiheila": {
        "label": "开黑啦 Kook",
        "package": "nonebot-adapter-kaiheila",
        "import_line": "from nonebot.adapters.kaiheila import Adapter as KookAdapter",
        "register": "driver.register_adapter(KookAdapter)",
    },
    "none": {
        "label": "无适配器（仅测试）",
        "package": "",
        "import_line": "",
        "register": "",
    },
}


BOT_PY_TEMPLATE = '''\
"""
NoneBot2 机器人入口（由 NoneBot2 WebUI 生成并托管）
"""

import json
import sys
from pathlib import Path

import nonebot

BOT_ROOT = Path(__file__).resolve().parent
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

nonebot.init()

# ---------- 注册适配器 ----------
{adapter_imports}
driver = nonebot.get_driver()
{adapter_registers}


# ---------- WebUI 插件加载（支持启用/暂停） ----------
def _webui_load_plugins(plugin_dirs):
    """加载插件目录中的插件，跳过 WebUI 中暂停的插件。"""
    import pkgutil
    from nonebot.plugin import _managers
    from nonebot.plugin.manager import PluginManager

    disabled = set()
    disabled_file = BOT_ROOT / "webui_disabled_plugins.json"
    if disabled_file.exists():
        try:
            disabled = set(json.loads(disabled_file.read_text(encoding="utf-8")))
        except Exception:
            disabled = set()

    def _rel(d):
        d = Path(d).resolve()
        try:
            return d.relative_to(BOT_ROOT.resolve())
        except ValueError:
            return d

    search_path = []
    modules = []
    for d in plugin_dirs:
        d = Path(d).resolve()
        if not d.exists():
            continue
        search_path.append(str(_rel(d)))
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
        for info in pkgutil.iter_modules([str(d)]):
            name = info.name
            if not name.startswith("_") and name not in disabled:
                modules.append(name)

    class _FilteredManager(PluginManager):
        def __init__(self, disabled, **kw):
            self._disabled = set(disabled)
            super().__init__(**kw)

        def _prepare_plugins(self):
            result = super()._prepare_plugins()
            for pid in list(self._searched_plugin_ids):
                short = self._searched_plugin_ids[pid].rsplit(".", 1)[-1]
                if pid in self._disabled or short in self._disabled:
                    self._searched_plugin_ids.pop(pid, None)
            return self.available_plugins

    if not search_path:
        return
    try:
        manager = _FilteredManager(disabled, search_path=search_path)
        _managers.append(manager)
        loader = getattr(manager, "load_all_plugins", None)
        if loader is None:
            raise AttributeError
        loader()
    except AttributeError:
        # 兼容旧版 NoneBot：直接按模块名加载
        manager = PluginManager(plugins=modules)
        _managers.append(manager)
        if hasattr(manager, "load_all_plugins"):
            manager.load_all_plugins()
        else:
            manager.load_plugins()


_webui_load_plugins({plugin_dirs!r})


if __name__ == "__main__":
    nonebot.run()
'''


EXISTING_ENTRY_TEMPLATE = '''\
"""NoneBot2 机器人入口（由 NoneBot2 WebUI 为已有项目自动生成）"""

import nonebot

{adapter_imports}

nonebot.init()
driver = nonebot.get_driver()
{adapter_registers}
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
'''


ENV_TEMPLATE = """\
# NoneBot2 配置（由 NoneBot2 WebUI 管理）
HOST={host}
PORT={port}
DRIVER=~fastapi+~websockets
LOG_LEVEL=INFO
SUPERUSERS=[]
"""


PYPROJECT_TEMPLATE = """\
[project]
name = "{name}"
version = "0.1.0"
description = "NoneBot2 项目（由 NoneBot2 WebUI 创建）"
requires-python = ">=3.9"
dependencies = [
    "nonebot2[fastapi,httpx,websockets]",
{adapter_deps}
]

[tool.nonebot]
plugin_dirs = {plugin_dirs}
builtin_plugins = ["echo"]

[tool.nonebot.plugins]
"""


BOT_GITIGNORE = """\
.env
.env.*
!.env.example
.venv/
venv/
__pycache__/
*.py[cod]
*.log
data/
"""


BOT_README = """\
# {name}

由 [NoneBot2 WebUI](https://nonebot.dev/) 创建的 NoneBot2 机器人项目。

## 运行

```bash
python bot.py
```

或在项目目录下使用 [nb-cli](https://cli.nonebot.dev/) 管理：

```bash
nb run
```

## 插件

- 本地插件目录：`{plugin_dir}`
- 通过 WebUI 可安装/启用/暂停插件
- `webui_disabled_plugins.json` 记录被暂停的插件
"""


class BotManager:
    """机器人注册表管理。"""

    def __init__(self) -> None:
        self._bots: Dict[str, Bot] = {}
        self._lock = threading.RLock()
        self.load()

    # ---------- 注册表 ----------
    def load(self) -> None:
        with self._lock:
            raw = load_json(config.BOTS_FILE, []) or []
            self._bots = {b["id"]: Bot(**b) for b in raw}

    def save(self) -> None:
        with self._lock:
            save_json(
                config.BOTS_FILE,
                [b.model_dump() for b in sorted(self._bots.values(), key=lambda x: x.created_at)],
            )

    def list_bots(self) -> list[Bot]:
        with self._lock:
            return sorted(self._bots.values(), key=lambda x: x.created_at)

    def get_bot(self, bot_id: str) -> Optional[Bot]:
        with self._lock:
            return self._bots.get(bot_id)

    def update_bot(self, bot: Bot) -> None:
        with self._lock:
            bot.updated_at = _now()
            self._bots[bot.id] = bot
            self.save()

    def remove_bot(self, bot_id: str) -> None:
        with self._lock:
            self._bots.pop(bot_id, None)
            self.save()

    # ---------- 创建 ----------
    def create_bot(
        self,
        data: BotCreate,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Bot:
        bot_dir = Path(data.directory).expanduser().resolve()
        exists_non_empty = bot_dir.exists() and any(bot_dir.iterdir())

        bot = Bot(
            id=uuid.uuid4().hex[:12],
            name=data.name,
            directory=str(bot_dir),
            adapter=data.adapter,
            host=data.host,
            port=data.port,
            python=data.python,
            plugin_dir=data.plugin_dir,
            auto_start=data.auto_start,
            managed=not exists_non_empty,
            status="creating",
            created_at=_now(),
            updated_at=_now(),
            extra={"create_dir": data.create_dir},
        )
        with self._lock:
            self._bots[bot.id] = bot
            self.save()

        # 后台线程执行创建流程（虚拟环境、依赖安装等耗时操作）
        t = threading.Thread(
            target=self._create_worker,
            args=(bot, data, exists_non_empty, log_callback),
            daemon=True,
            name=f"create-bot-{bot.name}",
        )
        t.start()
        return bot

    def _create_worker(
        self,
        bot: Bot,
        data: BotCreate,
        exists_non_empty: bool,
        log_callback: Optional[Callable[[str, str], None]],
    ) -> None:
        def log(msg: str) -> None:
            if log_callback:
                log_callback(bot.id, msg)

        try:
            bot_dir = Path(bot.directory)

            if exists_non_empty:
                # 已有项目：采用现有目录，不重建脚手架
                log(f"检测到目录已存在非空项目，直接采用现有项目：{bot_dir}")
                venv = self._find_venv(bot_dir)
                bot.venv = str(venv) if venv else ""
                bot.python = self._resolve_python(bot_dir, bot.python)
                bot.status = "stopped"
                bot.managed = False
                self.update_bot(bot)
                log("已注册现有项目")
                try:
                    self.ensure_bot_entry(bot, log)
                    self.sync_plugin_dir(bot, log)
                except Exception as exc:  # noqa: BLE001
                    # 入口/目录同步失败不影响注册本身，启动时会自动重试
                    log(f"入口/插件目录同步失败：{exc}（启动时会自动重试）")
                return

            if not bot_dir.exists():
                bot_dir.mkdir(parents=True, exist_ok=True)
                log(f"创建目录：{bot_dir}")

            # 1. 创建虚拟环境
            base_python = data.python.strip() or sys.executable
            log(f"使用 Python：{base_python}")
            venv_dir = bot_dir / ".venv"
            log("创建虚拟环境 .venv ...")
            proc = subprocess.run(
                [base_python, "-m", "venv", str(venv_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"创建虚拟环境失败：\n{proc.stderr[-2000:]}")
            log("虚拟环境创建完成")

            venv_python = self._venv_python(venv_dir)
            bot.venv = str(venv_dir)
            bot.python = str(venv_python)

            # 2. 生成项目文件
            adapter = ADAPTERS.get(bot.adapter)
            if adapter is None:
                raise RuntimeError(f"不支持的适配器：{bot.adapter}")
            packages = ["nonebot2[fastapi,httpx,websockets]"]
            if adapter["package"]:
                packages.append(adapter["package"])

            plugin_dir = Path(bot.plugin_dir)
            if not plugin_dir.is_absolute():
                plugin_dir = bot_dir / plugin_dir
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "__init__.py").touch(exist_ok=True)

            bot_py = BOT_PY_TEMPLATE.format(
                adapter_imports=adapter["import_line"],
                adapter_registers=adapter["register"],
                plugin_dirs=[str(plugin_dir)],
            )
            adapter_dep = ""
            if adapter["package"]:
                adapter_dep = f'    "{adapter["package"]}",'
            try:
                rel_plugin_dir = str(plugin_dir.relative_to(bot_dir))
            except ValueError:
                rel_plugin_dir = str(plugin_dir)
            rel_plugin_dir = rel_plugin_dir.replace("\\", "/")
            pyproject = PYPROJECT_TEMPLATE.format(
                name=bot.name,
                adapter_deps=adapter_dep,
                plugin_dirs=json.dumps([rel_plugin_dir]),
            )
            (bot_dir / "bot.py").write_text(bot_py, encoding="utf-8")
            (bot_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")
            (bot_dir / ".env").write_text(
                ENV_TEMPLATE.format(host=bot.host, port=bot.port),
                encoding="utf-8",
            )
            (bot_dir / ".gitignore").write_text(BOT_GITIGNORE, encoding="utf-8")
            (bot_dir / "README.md").write_text(
                BOT_README.format(name=bot.name, plugin_dir=rel_plugin_dir),
                encoding="utf-8",
            )
            (bot_dir / "webui_disabled_plugins.json").write_text(
                "[]", encoding="utf-8"
            )
            log("已生成 bot.py / pyproject.toml / .env / 插件目录")

            # 3. 安装依赖
            log(f"安装依赖：{' '.join(packages)}")
            self._run_pip(venv_python, packages, log)
            log("依赖安装完成")

            bot.status = "stopped"
            self.update_bot(bot)
            log("机器人创建完成")
        except Exception as exc:  # noqa: BLE001
            bot.status = "error"
            bot.extra["error"] = str(exc)
            self.update_bot(bot)
            log(f"创建失败：{exc}")

    def _run_pip(
        self, venv_python: Path, packages: list[str], log: Callable[[str], None]
    ) -> None:
        """执行 pip 安装并实时输出日志。"""
        cmd = [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check"]
        cmd += packages
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            if line.strip():
                log(line)
        proc.wait(timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"pip 安装失败（退出码 {proc.returncode}）")

    # ---------- 路径工具 ----------
    @staticmethod
    def _venv_python(venv_dir: Path) -> Path:
        if os.name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    @staticmethod
    def _find_venv(bot_dir: Path) -> Optional[Path]:
        for name in (".venv", "venv", "env"):
            p = bot_dir / name
            if (BotManager._venv_python(p)).exists():
                return p
        return None

    @staticmethod
    def _resolve_python(bot_dir: Path, python: str) -> str:
        if python.strip():
            return python.strip()
        venv = BotManager._find_venv(bot_dir)
        if venv:
            return str(BotManager._venv_python(venv))
        return shutil.which("python") or sys.executable

    @staticmethod
    def _pyproject_nonebot_adapters(bot_dir: Path) -> Optional[list[str]]:
        """解析 pyproject.toml 的 [tool.nonebot]，返回适配器模块名列表。

        返回 None 表示没有 pyproject.toml 或不是 NoneBot 项目（无法自动生成入口）；
        返回空列表表示是 NoneBot 项目但未在 pyproject 中声明适配器。
        """
        pyproject = bot_dir / "pyproject.toml"
        if not pyproject.exists():
            return None
        try:
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
        except Exception:  # noqa: BLE001 - TOML 解析失败按非 NoneBot 项目处理
            return None
        tool_nonebot = (data.get("tool") or {}).get("nonebot")
        if not isinstance(tool_nonebot, dict):
            return None
        modules: list[str] = []
        adapters = tool_nonebot.get("adapters")
        if isinstance(adapters, dict):
            specs_iter = adapters.values()
        elif isinstance(adapters, list):
            # 兼容 [tool.nonebot] 下 adapters = [{...}] 的列表格式
            specs_iter = adapters
        else:
            specs_iter = []
        for specs in specs_iter:
            if isinstance(specs, list):
                for spec in specs:
                    if isinstance(spec, dict) and spec.get("module_name"):
                        modules.append(str(spec["module_name"]))
            elif isinstance(specs, dict):
                if specs.get("module_name"):
                    modules.append(str(specs["module_name"]))
        return modules

    @staticmethod
    def _pyproject_nonebot_plugin_dirs(bot_dir: Path) -> Optional[list[str]]:
        """解析 pyproject.toml 的 [tool.nonebot] plugin_dirs，返回规范化路径列表。

        返回 None 表示没有 pyproject.toml 或未声明 plugin_dirs。
        """
        pyproject = bot_dir / "pyproject.toml"
        if not pyproject.exists():
            return None
        try:
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
        except Exception:  # noqa: BLE001 - TOML 解析失败按未声明处理
            return None
        tool_nonebot = (data.get("tool") or {}).get("nonebot")
        if not isinstance(tool_nonebot, dict):
            return None
        raw = tool_nonebot.get("plugin_dirs")
        if not isinstance(raw, list):
            return None
        dirs: list[str] = []
        for d in raw:
            if not isinstance(d, str) or not d.strip():
                continue
            p = Path(d).expanduser()
            if not p.is_absolute():
                p = bot_dir / p
            try:
                rel = p.resolve().relative_to(bot_dir.resolve())
                dirs.append(rel.as_posix())
            except ValueError:
                dirs.append(str(p))
        return dirs or None

    def ensure_bot_entry(
        self, bot: Bot, log: Optional[Callable[[str], None]] = None
    ) -> bool:
        """确保已有项目有可启动的 bot.py，缺失时按 pyproject.toml 自动生成标准入口。"""
        bot_dir = Path(bot.directory)
        entry = bot_dir / "bot.py"
        if entry.exists():
            return True
        modules = self._pyproject_nonebot_adapters(bot_dir)
        if modules is None:
            # 没有 pyproject.toml 或不是 NoneBot 项目，无法自动生成
            return False
        imports, registers = [], []
        if modules:
            for i, module in enumerate(modules):
                imports.append(f"from {module} import Adapter as _Adapter{i}")
                registers.append(f"driver.register_adapter(_Adapter{i})")
        else:
            # pyproject 未声明适配器时，回退到 WebUI 注册时选择的适配器
            adapter = ADAPTERS.get(bot.adapter)
            if not adapter or not adapter["import_line"]:
                return False
            imports.append(adapter["import_line"])
            registers.append(adapter["register"])
        entry.write_text(
            EXISTING_ENTRY_TEMPLATE.format(
                adapter_imports="\n".join(imports),
                adapter_registers="\n".join(registers),
            ),
            encoding="utf-8",
        )
        if log:
            log("未检测到 bot.py，已根据 pyproject.toml 自动生成标准入口")
        return True

    def sync_plugin_dir(
        self, bot: Bot, log: Optional[Callable[[str], None]] = None
    ) -> bool:
        """已有项目：按 pyproject.toml 的 plugin_dirs 同步 WebUI 记录的插件目录。

        已有项目的实际插件加载以项目自己的 pyproject.toml 为准，WebUI 的
        插件列表/上传目录应与之保持一致，否则会一直停留在默认的 src/plugins。
        """
        dirs = self._pyproject_nonebot_plugin_dirs(Path(bot.directory))
        if not dirs:
            return False
        target = dirs[0]
        if bot.plugin_dir == target:
            return False
        old = bot.plugin_dir
        bot.plugin_dir = target
        self.update_bot(bot)
        if log:
            log(f"按 pyproject.toml 同步插件目录：{old} -> {target}")
        return True

    # ---------- 配置 ----------
    def read_env(self, bot: Bot) -> str:
        env_file = Path(bot.directory) / ".env"
        if env_file.exists():
            return env_file.read_text(encoding="utf-8")
        return ""

    def write_env(self, bot: Bot, content: str) -> None:
        env_file = Path(bot.directory) / ".env"
        env_file.write_text(content, encoding="utf-8")

    def read_bot_py(self, bot: Bot) -> str:
        f = Path(bot.directory) / "bot.py"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    def plugin_dir_path(self, bot: Bot) -> Path:
        p = Path(bot.plugin_dir)
        if p.is_absolute():
            return p
        return (Path(bot.directory) / p).resolve()


# 全局单例
bot_manager = BotManager()
