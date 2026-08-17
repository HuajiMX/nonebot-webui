"""版本检查：从发布源获取最新版本并与本地版本对比。"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from typing import Optional

from . import __version__, config


_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL = 30 * 60  # 30 分钟
_LOCK = threading.Lock()

# 发布源默认值：发布前把 DEFAULT_UPDATE_REPO 改成你的仓库（owner/repo）。
# data/config.json 中的 update_repo / update_url / update_asset 可覆盖。
DEFAULT_UPDATE_REPO = "HuajiMX/nonebot-webui"
DEFAULT_UPDATE_URL = ""
DEFAULT_UPDATE_ASSET = "nonebot-webui.zip"


def _read_update_config() -> dict:
    cfg = {}
    if config.CONFIG_FILE.exists():
        try:
            cfg = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cfg = {}
    return {
        "update_repo": str(cfg.get("update_repo") or DEFAULT_UPDATE_REPO).strip(),
        "update_url": str(cfg.get("update_url") or DEFAULT_UPDATE_URL).strip(),
        "update_asset": (
            str(cfg.get("update_asset") or DEFAULT_UPDATE_ASSET).strip()
            or "nonebot-webui.zip"
        ),
    }


def _http_json(url: str, timeout: float = 10) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "nonebot-webui/update-check"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def _version_tuple(version: str) -> tuple:
    return tuple(int(x) for x in (re.findall(r"\d+", version or "")[:4]))


def _do_check() -> dict:
    cfg = _read_update_config()
    current = __version__
    info = None
    if cfg["update_url"]:
        data = _http_json(cfg["update_url"])
        if data:
            info = {
                "version": str(data.get("version") or ""),
                "download_url": str(data.get("download_url") or ""),
                "notes": str(data.get("notes") or ""),
            }
    elif cfg["update_repo"]:
        data = _http_json(
            f"https://api.github.com/repos/{cfg['update_repo']}/releases/latest"
        )
        if data:
            download_url = ""
            for asset in data.get("assets") or []:
                if asset.get("name") == cfg["update_asset"]:
                    download_url = asset.get("browser_download_url") or ""
                    break
            info = {
                "version": str(data.get("tag_name") or "").lstrip("v"),
                "download_url": download_url,
                "notes": str(data.get("body") or ""),
            }
    if not info or not info["version"]:
        return {
            "current": current,
            "latest": "",
            "has_update": False,
            "notes": "",
            "download_url": "",
        }
    return {
        "current": current,
        "latest": info["version"],
        "has_update": _version_tuple(info["version"]) > _version_tuple(current),
        "notes": info["notes"],
        "download_url": info["download_url"],
    }


def check_update(force: bool = False) -> dict:
    """返回更新检查结果（带 30 分钟缓存）。"""
    with _LOCK:
        if (
            not force
            and _CACHE["data"] is not None
            and time.time() - _CACHE["ts"] < _CACHE_TTL
        ):
            return _CACHE["data"]
        result = _do_check()
        _CACHE["ts"] = time.time()
        _CACHE["data"] = result
        return result
