"""基于 JSON 文件的轻量持久化存储（原子写入）。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


_lock = threading.RLock()


def load_json(path: Path, default: Any = None) -> Any:
    """读取 JSON 文件，不存在或损坏时返回 default。"""
    with _lock:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 文件损坏时备份后返回默认值
            try:
                path.rename(path.with_suffix(".bak.json"))
            except OSError:
                pass
            return default


def save_json(path: Path, data: Any) -> None:
    """原子写入 JSON 文件。"""
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
