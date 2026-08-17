"""服务器监控接口。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..deps import ws_auth
from ..monitor import snapshot


router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("")
def get_snapshot() -> dict:
    return snapshot()


@router.websocket("/ws")
async def monitor_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await ws_auth(websocket)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="未认证")
        return
    try:
        while True:
            await websocket.send_json(snapshot())
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
