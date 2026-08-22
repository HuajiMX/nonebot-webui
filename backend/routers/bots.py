"""机器人管理接口。"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ..bot_manager import ADAPTERS, bot_manager
from ..deps import current_user
from ..models import BotCreate, BotUpdate, ConfigUpdate
from ..process_manager import process_manager


router = APIRouter(prefix="/api/bots", tags=["bots"])


def _get_bot_or_404(bot_id: str):
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="机器人不存在")
    return bot


@router.get("/adapters")
def list_adapters(_: str = Depends(current_user)) -> dict:
    """支持的协议/适配器列表。"""
    return {
        "adapters": [
            {"value": k, "label": v["label"], "package": v["package"]}
            for k, v in ADAPTERS.items()
        ]
    }


@router.get("")
def list_bots(_: str = Depends(current_user)) -> list[dict]:
    bots = []
    for bot in bot_manager.list_bots():
        data = bot.model_dump()
        data["running"] = process_manager.is_running(bot.id)
        if data["running"]:
            data["status"] = "running"
        bots.append(data)
    return bots


@router.post("", status_code=201)
def create_bot(data: BotCreate, _: str = Depends(current_user)) -> dict:
    # 检查同名
    if any(b.name == data.name for b in bot_manager.list_bots()):
        raise HTTPException(status_code=400, detail="已存在同名机器人")
    bot = bot_manager.create_bot(
        data,
        log_callback=lambda bot_id, msg: process_manager._feed(
            bot_id, {"type": "log", "data": msg, "ts": time.time()}
        ),
    )
    return bot.model_dump()


@router.post("/pick-directory")
def pick_directory(_: str = Depends(current_user)) -> dict:
    """打开系统文件夹选择对话框，返回所选目录（仅 Windows 本地使用）。"""
    from ..folder_picker import pick_folder

    path = pick_folder()
    return {"directory": path, "supported": os.name == "nt"}


@router.get("/{bot_id}")
def get_bot(bot_id: str, _: str = Depends(current_user)) -> dict:
    bot = _get_bot_or_404(bot_id)
    data = bot.model_dump()
    data["running"] = process_manager.is_running(bot_id)
    data["directory_exists"] = Path(bot.directory).exists()
    data["adapter_label"] = ADAPTERS.get(bot.adapter, {}).get("label", bot.adapter)
    return data


@router.patch("/{bot_id}")
def update_bot(bot_id: str, data: BotUpdate, _: str = Depends(current_user)) -> dict:
    bot = _get_bot_or_404(bot_id)
    changed = data.model_dump(exclude_unset=True)
    host_port_changed = "host" in changed or "port" in changed
    if "name" in changed:
        name = (changed["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="名称不能为空")
        if any(b.name == name and b.id != bot_id for b in bot_manager.list_bots()):
            raise HTTPException(status_code=400, detail="已存在同名机器人")
        bot.name = name
    for field in ("host", "port", "terminal_command", "auto_start", "plugin_dir"):
        if field in changed and changed[field] is not None:
            setattr(bot, field, changed[field])
    if "adapter" in changed and changed["adapter"]:
        if changed["adapter"] not in ADAPTERS:
            raise HTTPException(status_code=400, detail="不支持的适配器")
        bot.adapter = changed["adapter"]
    if host_port_changed:
        try:
            bot_manager.sync_env_host_port(bot)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"写入 .env 失败：{exc}") from exc
    bot_manager.update_bot(bot)
    return bot.model_dump()


@router.delete("/{bot_id}")
def delete_bot(
    bot_id: str,
    remove_dir: bool = Query(default=False),
    _: str = Depends(current_user),
) -> dict:
    bot = _get_bot_or_404(bot_id)
    try:
        process_manager.stop(bot_id)
    except Exception:  # noqa: BLE001
        pass
    bot_dir = Path(bot.directory).resolve()
    if remove_dir:
        if not bot_dir.exists():
            raise HTTPException(status_code=400, detail="目录不存在，无需删除")
        if bot_dir == Path(bot_dir.anchor).resolve():
            raise HTTPException(status_code=400, detail="拒绝删除盘符根目录")
        shutil.rmtree(bot_dir, ignore_errors=True)
    bot_manager.remove_bot(bot_id)
    process_manager.clear_logs(bot_id)
    return {"ok": True, "removed_dir": remove_dir}


@router.post("/{bot_id}/start")
def start_bot(bot_id: str, _: str = Depends(current_user)) -> dict:
    bot = _get_bot_or_404(bot_id)
    if process_manager.is_running(bot_id):
        raise HTTPException(status_code=400, detail="机器人已在运行")
    try:
        process_manager.start(bot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "status": "running"}


@router.post("/{bot_id}/stop")
def stop_bot(bot_id: str, _: str = Depends(current_user)) -> dict:
    _get_bot_or_404(bot_id)
    process_manager.stop(bot_id)
    return {"ok": True, "status": "stopped"}


@router.post("/{bot_id}/restart")
def restart_bot(bot_id: str, _: str = Depends(current_user)) -> dict:
    bot = _get_bot_or_404(bot_id)
    if process_manager.is_running(bot_id):
        process_manager.restart(bot_id)
    else:
        process_manager.start(bot_id)
    return {"ok": True, "status": "running"}


@router.get("/{bot_id}/config")
def get_config(bot_id: str, _: str = Depends(current_user)) -> dict:
    bot = _get_bot_or_404(bot_id)
    return {
        "env": bot_manager.read_env(bot),
        "bot_py": bot_manager.read_bot_py(bot),
        "plugin_dir": bot.plugin_dir,
    }


@router.put("/{bot_id}/config")
def put_config(
    bot_id: str,
    data: ConfigUpdate,
    _: str = Depends(current_user),
) -> dict:
    bot = _get_bot_or_404(bot_id)
    bot_manager.write_env(bot, data.content)
    return {"ok": True}
