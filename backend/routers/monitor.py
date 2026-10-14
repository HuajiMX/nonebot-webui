"""服务器监控接口。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..deps import current_user, ws_auth
from ..monitor import snapshot


router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("")
def get_snapshot(_: str = Depends(current_user)) -> dict:
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
            # snapshot() 会同步遍历系统全部进程：Windows 上实测可达 11 s，Linux 约 12 ms。
            # 一旦直接在事件循环里调用，就会阻塞**所有**其它请求（前端表现为
            # “网络错误，请检查服务是否启动”），因此统一丢到工作线程执行。
            data = await asyncio.to_thread(snapshot)
            await websocket.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
