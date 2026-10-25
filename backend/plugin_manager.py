"""插件管理：列表、启用/暂停、上传安装（.py / .zip）。"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

from .bot_manager import bot_manager


PLUGIN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_PLUGIN_ZIP_ENTRIES = 5000
MAX_PLUGIN_ZIP_TOTAL = 300 * 1024 * 1024  # 解压后总大小上限 300MB
DISABLED_DIRNAME = ".webui_disabled"  # 被暂停插件的隔离目录（NoneBot 不会扫描到这里）


class PluginInfo:
    def __init__(
        self,
        name: str,
        path: str,
        kind: str,
        disabled: bool,
        size: int,
        mtime: float,
        description: str = "",
        display_name: str = "",
    ) -> None:
        self.name = name
        self.path = path
        self.kind = kind
        self.disabled = disabled
        self.size = size
        self.mtime = mtime
        self.description = description
        self.display_name = display_name

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "is_visual": self.name.startswith("vplugin_"),
            "path": self.path,
            "kind": self.kind,
            "disabled": self.disabled,
            "enabled": not self.disabled,
            "size": self.size,
            "mtime": self.mtime,
            "description": self.description,
        }


def _read_docstring(path: Path) -> str:
    """读取 Python 文件模块级 docstring 作为插件描述。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        doc = ast.get_docstring(tree)
        if doc:
            return doc.strip().split("\n")[0][:120]
    except (SyntaxError, OSError):
        return ""
    return ""


def _read_plugin_display_name(path: Path) -> str:
    """读取插件文件中声明的显示名（PLUGIN_NAME = "..."），没有则返回空串。

    可视化插件生成的文件名为 vplugin_xxxx.py，但代码里声明了真实的
    插件名称（PLUGIN_NAME），列表展示时用它代替模块名。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return ""
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PLUGIN_NAME"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            name = node.value.value.strip()
            return name[:120]
    return ""


def _disabled_set_of(bot) -> set[str]:
    f = Path(bot.directory) / "webui_disabled_plugins.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_disabled_of(bot, disabled: set[str]) -> None:
    f = Path(bot.directory) / "webui_disabled_plugins.json"
    f.write_text(json.dumps(sorted(disabled), ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 暂停/启用：把插件源码移入/移出隔离目录
#
# 只写 webui_disabled_plugins.json 是不够的：该文件只有 WebUI 生成的托管入口
# （bot.py 里的 _webui_load_plugins）会读取，注册的已有项目、自己手写的 bot.py
# 以及任何外部启动方式都不读它，插件里的定时任务会继续触发。把源码移入
# .webui_disabled/ 后，NoneBot 的插件扫描（pkgutil.iter_modules / plugin_dirs）
# 根本发现不了该插件，暂停因此对所有入口生效。
# ---------------------------------------------------------------------------


def _live_path(plugin_dir: Path, name: str) -> Optional[Path]:
    """插件目录里可被 NoneBot 加载的源码路径（.py 文件或插件包目录）。"""
    f = plugin_dir / f"{name}.py"
    if f.is_file():
        return f
    d = plugin_dir / name
    if d.is_dir() and (d / "__init__.py").exists():
        return d
    return None


def _disabled_dir(plugin_dir: Path) -> Path:
    return plugin_dir / DISABLED_DIRNAME


def _quarantined_path(plugin_dir: Path, name: str) -> Optional[Path]:
    """隔离目录里的插件源码路径。"""
    q = _disabled_dir(plugin_dir)
    if not q.is_dir():
        return None
    for cand in (q / f"{name}.py", q / name):
        if cand.is_file() or (cand.is_dir() and (cand / "__init__.py").exists()):
            return cand
    return None


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _move_to_disabled(plugin_dir: Path, path: Path) -> Path:
    q = _disabled_dir(plugin_dir)
    q.mkdir(parents=True, exist_ok=True)
    target = q / path.name
    if target.exists():
        _remove_path(target)
    shutil.move(str(path), str(target))
    return target


def _restore_from_disabled(plugin_dir: Path, path: Path) -> Path:
    target = plugin_dir / path.name
    if target.exists():
        _remove_path(target)
    shutil.move(str(path), str(target))
    return target


def _entry_plugin_name(entry: Path) -> str:
    if entry.is_dir():
        return entry.name
    return entry.stem if entry.suffix == ".py" else ""


def _sync_disabled_of(bot) -> set[str]:
    """让暂停状态在文件层面生效，并返回最新的暂停集合（含历史数据迁移）。"""
    plugin_dir = bot_manager.plugin_dir_path(bot)
    if not plugin_dir.is_dir():
        return _disabled_set_of(bot)

    disabled = _disabled_set_of(bot)
    changed = False
    # 历史版本只写 JSON 没移文件：这里补做迁移，使旧数据也能真正暂停
    for name in sorted(disabled):
        live = _live_path(plugin_dir, name)
        if live is not None:
            _move_to_disabled(plugin_dir, live)
            changed = True

    # 隔离目录里有但 JSON 没记录的（异常状态）：按暂停处理并补登记
    q = _disabled_dir(plugin_dir)
    if q.is_dir():
        for entry in q.iterdir():
            name = _entry_plugin_name(entry)
            if name and PLUGIN_NAME_RE.match(name) and name not in disabled:
                disabled.add(name)
                changed = True

    if changed:
        _save_disabled_of(bot, disabled)
    return disabled


def sync_disabled_files(bot_id: str) -> set[str]:
    """启动机器人前调用：确保暂停的插件不会被任何入口加载。"""
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    return _sync_disabled_of(bot)


def _plugin_info(entry: Path, name: str, kind: str, disabled: bool) -> PluginInfo:
    is_pkg = kind == "package"
    return PluginInfo(
        name=name,
        path=str(entry),
        kind=kind,
        disabled=disabled,
        size=_dir_size(entry) if is_pkg else entry.stat().st_size,
        mtime=entry.stat().st_mtime,
        description=_read_docstring(entry / "__init__.py" if is_pkg else entry),
        display_name="" if is_pkg else _read_plugin_display_name(entry),
    )


def list_plugins(bot_id: str) -> list[dict]:
    """扫描机器人插件目录，返回插件列表（暂停的插件来自隔离目录）。"""
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    plugin_dir = bot_manager.plugin_dir_path(bot)
    if not plugin_dir.exists():
        return []

    disabled = _sync_disabled_of(bot)
    result: dict[str, PluginInfo] = {}
    for entry in sorted(plugin_dir.iterdir(), key=lambda x: x.name.lower()):
        if entry.name.startswith("__") or entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix == ".py":
            name = entry.stem
            if not PLUGIN_NAME_RE.match(name):
                continue
            result[name] = _plugin_info(entry, name, "file", name in disabled)
        elif entry.is_dir() and (entry / "__init__.py").exists():
            name = entry.name
            if not PLUGIN_NAME_RE.match(name):
                continue
            result[name] = _plugin_info(entry, name, "package", name in disabled)

    q = _disabled_dir(plugin_dir)
    if q.is_dir():
        for entry in sorted(q.iterdir(), key=lambda x: x.name.lower()):
            name = _entry_plugin_name(entry)
            if not name or not PLUGIN_NAME_RE.match(name) or name in result:
                continue
            kind = "package" if entry.is_dir() else "file"
            if kind == "file" and not entry.is_file():
                continue
            result[name] = _plugin_info(entry, name, kind, True)

    return [result[k].to_dict() for k in sorted(result, key=str.lower)]


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def set_plugin_enabled(bot_id: str, plugin_name: str, enabled: bool) -> dict:
    """启用/暂停插件：暂停会把插件源码移入隔离目录，重启机器人后不再加载。"""
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    plugin_dir = bot_manager.plugin_dir_path(bot)
    _sync_disabled_of(bot)
    live = _live_path(plugin_dir, plugin_name)
    quarantined = _quarantined_path(plugin_dir, plugin_name)
    if live is None and quarantined is None:
        raise ValueError(f"插件不存在：{plugin_name}")

    disabled = _disabled_set_of(bot)
    try:
        if enabled:
            if quarantined is not None:
                _restore_from_disabled(plugin_dir, quarantined)
            disabled.discard(plugin_name)
        else:
            if live is not None:
                _move_to_disabled(plugin_dir, live)
            disabled.add(plugin_name)
    except OSError as exc:
        raise ValueError(f"移动插件文件失败（请确认插件目录可写）：{exc}") from exc
    _save_disabled_of(bot, disabled)
    return {"name": plugin_name, "enabled": enabled}


def remove_plugin_files(bot_id: str, plugin_name: str) -> bool:
    """删除插件源码（含隔离目录里的副本）并清除暂停记录。"""
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    plugin_dir = bot_manager.plugin_dir_path(bot)
    removed = False
    for path in (
        _live_path(plugin_dir, plugin_name),
        _quarantined_path(plugin_dir, plugin_name),
    ):
        if path is not None:
            _remove_path(path)
            removed = True
    disabled = _disabled_set_of(bot)
    if plugin_name in disabled:
        disabled.discard(plugin_name)
        _save_disabled_of(bot, disabled)
    return removed


def install_plugin_file(bot_id: str, filename: str, content: bytes) -> dict:
    """安装单个 .py 插件文件。"""
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    plugin_dir = bot_manager.plugin_dir_path(bot)
    plugin_dir.mkdir(parents=True, exist_ok=True)

    name = Path(filename).name
    if not name.endswith(".py"):
        raise ValueError("仅支持 .py 插件文件")
    stem = name[:-3]
    if not PLUGIN_NAME_RE.match(stem):
        raise ValueError("插件文件名必须为合法 Python 模块名")

    # 语法校验
    try:
        ast.parse(content.decode("utf-8", errors="replace"))
    except SyntaxError as exc:
        raise ValueError(f"插件文件语法错误：{exc}") from exc

    target = plugin_dir / name
    # 覆盖安装时清掉隔离目录里的旧副本，避免两份源码并存
    stale = _quarantined_path(plugin_dir, stem)
    if stale is not None:
        _remove_path(stale)
    target.write_bytes(content)
    # 插件此前被暂停：保持暂停，写入后立刻移入隔离目录
    disabled = _disabled_set_of(bot)
    if stem in disabled:
        target = _move_to_disabled(plugin_dir, target)
    return {
        "name": stem,
        "path": str(target),
        "disabled": stem in disabled,
        "message": f"插件 {stem} 安装成功" + ("（保持暂停状态）" if stem in disabled else ""),
    }


def install_plugin_zip(
    bot_id: str,
    filename: str,
    content: bytes,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    """安装 .zip 插件包。

    支持两种形式：
    1. 源码包：解压到插件目录（单文件 .py / 插件包目录 / 带 pyproject.toml 的项目）
    2. 打包插件：若含 pyproject.toml 或 setup.py，则优先通过 pip 安装到虚拟环境
    """
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    plugin_dir = bot_manager.plugin_dir_path(bot)
    plugin_dir.mkdir(parents=True, exist_ok=True)

    if not filename.lower().endswith(".zip"):
        raise ValueError("仅支持 .zip 压缩包")

    with tempfile.TemporaryDirectory(prefix="nbwebui_plugin_") as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                _safe_extract(zf, tmp_path)
        except zipfile.BadZipFile as exc:
            raise ValueError("无效的 zip 文件") from exc

        entries = list(tmp_path.rglob("*"))
        files = [p for p in entries if p.is_file()]
        if not files:
            raise ValueError("zip 包为空")

        # 检查是否为 pip 包（pyproject.toml / setup.py / setup.cfg）
        has_pyproject = any(
            p.name in ("pyproject.toml", "setup.py", "setup.cfg") for p in files
        )
        if has_pyproject and bot.python:
            if log:
                log("检测到 Python 打包配置，将通过 pip 安装到虚拟环境 ...")
            cmd = [bot.python, "-m", "pip", "install", "--disable-pip-version-check"]
            if log:
                # 先解压到临时目录再安装，方便输出日志
                cmd.append(str(tmp_path))
                _run(cmd, log)
            else:
                subprocess.run(cmd + [str(tmp_path)], capture_output=True, timeout=600)
            return {
                "message": "已通过 pip 安装到虚拟环境",
                "mode": "pip",
            }

        # 源码插件：复制到插件目录（保留目录结构）
        top_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
        root = tmp_path
        prefix = Path("")
        if len(top_dirs) == 1 and not [p for p in tmp_path.iterdir() if p.is_file()]:
            # 压缩包内只有单个顶层目录时，保留该目录名（插件包）
            root = top_dirs[0]
            prefix = Path(root.name)

        for p in sorted(root.rglob("*")):
            rel = prefix / p.relative_to(root)
            if p.is_file():
                # 排除打包元数据与缓存
                if p.name in ("pyproject.toml", "setup.py", "setup.cfg"):
                    continue
                if p.name == "requirements.txt" and bot.python:
                    if log:
                        log(f"安装依赖：{p.name}")
                    _run(
                        [bot.python, "-m", "pip", "install", "-r", str(p)],
                        log,
                    )
                    continue
                if p.suffix in (".pyc", ".pyo") or "__pycache__" in p.parts:
                    continue
                if p.name.startswith(".") or p.name == "__MACOSX":
                    continue
                target = plugin_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()
                shutil.copy2(p, target)
            elif p.is_dir():
                if p.name in ("__pycache__", ".git", "dist", "build", "__MACOSX"):
                    continue
                (plugin_dir / rel).mkdir(parents=True, exist_ok=True)

        # 统计实际安装的插件（插件目录根部的 .py 文件 / 含 __init__.py 的包）
        names = []
        for entry in sorted(plugin_dir.iterdir()):
            if entry.name.startswith("__") or entry.name.startswith("."):
                continue
            if entry.is_file() and entry.suffix == ".py" and PLUGIN_NAME_RE.match(entry.stem):
                names.append(entry.stem)
            elif entry.is_dir() and (entry / "__init__.py").exists():
                names.append(entry.name)
        names = sorted(set(names))
        # 已暂停的插件：覆盖安装后继续保持暂停（隔离目录里的旧副本换成新内容）
        disabled = _disabled_set_of(bot)
        for name in names:
            if name in disabled:
                live = _live_path(plugin_dir, name)
                if live is not None:
                    _move_to_disabled(plugin_dir, live)
        return {
            "message": (
                f"已安装 {len(names)} 个插件：{', '.join(names)}"
                if names
                else "压缩包内容已解压到插件目录"
            ),
            "mode": "source",
            "plugins": names,
        }


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    """安全解压，防止路径穿越与 zip 炸弹。"""
    target_root = target.resolve()
    entries = zf.infolist()
    if len(entries) > MAX_PLUGIN_ZIP_ENTRIES:
        raise ValueError("压缩包条目过多")
    total = 0
    for member in entries:
        total += member.file_size
        if total > MAX_PLUGIN_ZIP_TOTAL:
            raise ValueError("压缩包解压后总大小超过上限（300MB）")
        dest = (target / member.filename).resolve()
        if not dest.is_relative_to(target_root):
            raise ValueError(f"压缩包包含非法路径：{member.filename}")
    zf.extractall(target)


def _run(cmd: list[str], log: Optional[Callable[[str], None]]) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    creationflags = 0x08000000 if os.name == "nt" else 0
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
        if line.strip() and log:
            log(line)
    proc.wait(timeout=600)
    return proc.returncode
