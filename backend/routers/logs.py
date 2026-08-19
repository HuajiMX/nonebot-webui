"""机器人实时日志接口。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..bot_manager import bot_manager
from ..deps import current_user, ws_auth
from ..process_manager import process_manager


router = APIRouter(prefix="/api/bots", tags=["logs"])


@router.get("/{bot_id}/log")
def get_log(bot_id: str, _: str = Depends(current_user)) -> dict:
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="机器人不存在")
    return {"lines": process_manager.recent_logs(bot_id), "running": process_manager.is_running(bot_id)}


@router.websocket("/{bot_id}/log/ws")
async def log_ws(websocket: WebSocket, bot_id: str) -> None:
    await websocket.accept()
    try:
        await ws_auth(websocket)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="未认证")
        return
    if bot_manager.get_bot(bot_id) is None:
        await websocket.close(code=4404, reason="机器人不存在")
        return

    queue = process_manager.subscribe(bot_id)
    try:
        # 先发送历史日志
        for item in process_manager.recent_logs(bot_id):
            await websocket.send_json(item)
        while True:
            item = await queue.get()
            await websocket.send_json(item)
    except WebSocketDisconnect:
        pass
    finally:
        process_manager.unsubscribe(bot_id, queue)
