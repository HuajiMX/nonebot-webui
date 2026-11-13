"""可视化插件「数据存储」的面板侧读写。

数据文件与生成的插件放在同一目录：`vplugin_store_<模块名>.json`，结构与插件运行时一致：

    {"version": 1, "items": {"键": {"v": 值, "t": "2026-11-13 16:40:00"}}}

面板和机器人进程可能同时写同一个文件，所以这里所有写操作都遵守同一套规矩：

1. 先拿 `<文件>.lock` 的排他锁（插件运行时用的是同一个锁文件）；
2. 锁内重新读盘 → 只改目标键 → 写临时文件后 `os.replace` 原子替换。

这样不会把机器人在其它键上的改动整份覆盖掉，读到的也永远是完整 JSON。
"""

from __future__ import annotations

import datetime
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List

from .bot_manager import bot_manager


STORE_LIMIT_BYTES = 2 * 1024 * 1024
STORE_LIMIT_KEYS = 2000

# 只认可视化插件生成的模块名，杜绝路径穿越
MODULE_RE = re.compile(r"^vplugin_[0-9a-f]{6,32}$")
KEY_RE = re.compile(r"^[\w\-\u4e00-\u9fff]{1,64}$")

PREVIEW_LIMIT = 120


class StoreError(ValueError):
    """存储读写失败（消息直接给前端展示）。"""


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_path(bot_id: str, module: str) -> Path:
    """定位某个机器人下某个可视化插件的存储文件。"""
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise StoreError("机器人不存在")
    if not MODULE_RE.match(module or ""):
        raise StoreError("插件模块名不合法")
    return bot_manager.plugin_dir_path(bot) / f"vplugin_store_{module}.json"


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """与插件运行时共用 <文件>.lock 的排他锁，跨平台实现。"""
    handle = None
    try:
        handle = open(str(path) + ".lock", "a+b")
    except OSError:
        handle = None
    try:
        if handle is not None:
            try:
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                except ImportError:
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            except OSError:
                pass
        yield
    finally:
        if handle is not None:
            try:
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                handle.close()
            except OSError:
                pass


def _load(path: Path) -> Dict[str, dict]:
    try:
        with open(path, encoding="utf-8") as fp:
            raw = json.load(fp)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), dict):
        return {}
    return {k: v for k, v in raw["items"].items() if isinstance(v, dict)}


def _save(path: Path, items: Dict[str, dict]) -> None:
    payload = json.dumps(
        {"version": 1, "items": items}, ensure_ascii=False, indent=2, default=str
    )
    if len(payload.encode("utf-8")) > STORE_LIMIT_BYTES:
        raise StoreError(
            f"存储将超过上限 {STORE_LIMIT_BYTES // 1024} KB，本次修改已取消"
        )
    tmp = str(path) + ".tmp"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(tmp, "w", encoding="utf-8") as fp:
            fp.write(payload)
        os.replace(tmp, path)
    except OSError as exc:
        raise StoreError(f"写入存储文件失败：{exc}") from exc


def _validate_key(key: str) -> str:
    text = str(key or "").strip()
    if not text:
        raise StoreError("键名不能为空")
    if not KEY_RE.match(text):
        raise StoreError("键名只能包含中英文、数字、下划线、短横线，最多 64 个字符")
    return text


def _preview(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_LIMIT else text[: PREVIEW_LIMIT - 1] + "…"


def _describe(key: str, item: dict) -> dict:
    value = item.get("v")
    try:
        size = len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        size = 0
    return {
        "key": key,
        "type": type(value).__name__,
        "size": size,
        "updated": str(item.get("t") or ""),
        "preview": _preview(value),
        "json": json.dumps(value, ensure_ascii=False, indent=2, default=str),
    }


def read_store(bot_id: str, module: str) -> dict:
    path = resolve_path(bot_id, module)
    items = _load(path)
    rows: List[dict] = [_describe(k, items[k]) for k in sorted(items)]
    try:
        size = path.stat().st_size
        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except OSError:
        size = 0
        mtime = ""
    return {
        "exists": path.exists(),
        "module": module,
        "size": size,
        "mtime": mtime,
        "limit_bytes": STORE_LIMIT_BYTES,
        "limit_keys": STORE_LIMIT_KEYS,
        "count": len(rows),
        "items": rows,
    }


def write_key(bot_id: str, module: str, key: str, value: Any) -> dict:
    text = _validate_key(key)
    path = resolve_path(bot_id, module)
    with _file_lock(path):
        items = _load(path)
        if text not in items and len(items) >= STORE_LIMIT_KEYS:
            raise StoreError(f"键数量已达上限 {STORE_LIMIT_KEYS} 个，请先清理")
        items[text] = {"v": value, "t": _now()}
        _save(path, items)
    return _describe(text, items[text])


def delete_key(bot_id: str, module: str, key: str) -> bool:
    text = _validate_key(key)
    path = resolve_path(bot_id, module)
    with _file_lock(path):
        items = _load(path)
        if text not in items:
            return False
        items.pop(text)
        _save(path, items)
    return True


def clear_store(bot_id: str, module: str) -> int:
    """清空该插件的全部存储，返回清掉的键数量。"""
    path = resolve_path(bot_id, module)
    with _file_lock(path):
        items = _load(path)
        count = len(items)
        if count:
            _save(path, {})
    return count
