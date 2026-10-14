"""插件管理接口。"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..bot_manager import bot_manager
from ..deps import current_user
from ..plugin_manager import install_plugin_file, install_plugin_zip, list_plugins, set_plugin_enabled
from ..process_manager import process_manager


router = APIRouter(prefix="/api/bots", tags=["plugins"])


def _bot(bot_id: str):
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="机器人不存在")
    return bot


@router.get("/{bot_id}/plugins")
def get_plugins(bot_id: str, _: str = Depends(current_user)) -> dict:
    _bot(bot_id)
    return {
        "plugins": list_plugins(bot_id),
        "needs_restart": process_manager.is_running(bot_id),
    }


@router.put("/{bot_id}/plugins/{plugin_name}/enabled")
def set_enabled(
    bot_id: str,
    plugin_name: str,
    enabled: bool,
    auto_restart: bool = True,
    _: str = Depends(current_user),
) -> dict:
    bot = _bot(bot_id)
    try:
        result = set_plugin_enabled(bot_id, plugin_name, enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    restarted = False
    if auto_restart and process_manager.is_running(bot_id):
        try:
            process_manager.restart(bot_id)
            restarted = True
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"配置已保存，但重启失败：{exc}") from exc
    return {**result, "restarted": restarted}


@router.post("/{bot_id}/plugins/upload")
async def upload_plugin(
    bot_id: str,
    file: UploadFile = File(...),
    _: str = Depends(current_user),
) -> dict:
    _bot(bot_id)
    filename = file.filename or "plugin"
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（上限 50MB）")

    def _install() -> dict:
        if filename.lower().endswith(".zip"):
            return install_plugin_zip(
                bot_id,
                filename,
                content,
                log=lambda msg: process_manager._feed(
                    bot_id, {"type": "log", "data": msg, "ts": time.time()}
                ),
            )
        return install_plugin_file(bot_id, filename, content)

    try:
        # 安装过程中内部会执行 pip install（plugin_manager 里 wait 上限 600 s）。
        # 若在 async 处理器里同步执行，整个事件循环会停摆最长 10 分钟，全站接口
        # 一起超时（前端显示“网络错误，请检查服务是否启动”）。
        # process_manager._feed 是线程安全的（内部 RLock + 队列广播），
        # 故可安全地从工作线程推送进度日志。
        return await asyncio.to_thread(_install)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
