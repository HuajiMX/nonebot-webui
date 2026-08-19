"""内置终端接口（WebSocket）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..bot_manager import bot_manager
from ..deps import ws_auth
from ..terminal import bot_terminal_command, terminal_manager


router = APIRouter(prefix="/api/terminal", tags=["terminal"])


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        username = await ws_auth(websocket)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="未认证")
        return

    bot_id = websocket.query_params.get("bot_id", "")
    terminal_type = websocket.query_params.get("type", "bot")  # bot | protocol | custom
    command = websocket.query_params.get("command", "")

    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        await websocket.close(code=4404, reason="机器人不存在")
        return

    cwd = bot.directory
    if terminal_type == "bot":
        command, cwd = bot_terminal_command(bot_id)
    elif terminal_type == "protocol":
        command = bot.terminal_command or command
        if not command:
            await websocket.close(code=4400, reason="未配置协议端命令，请在机器人设置中填写 terminal_command")
            return
    # custom：使用 query command

    def _dim(value: str, default: int) -> int:
        try:
            return max(2, min(200, int(value)))
        except (TypeError, ValueError):
            return default

    rows = _dim(websocket.query_params.get("rows", "24"), 24)
    cols = _dim(websocket.query_params.get("cols", "80"), 80)

    session = terminal_manager.create(command=command, cwd=cwd, rows=rows, cols=cols)
    queue = session.attach(websocket.app.state.loop)

    await websocket.send_json({"type": "ready", "id": session.id, "command": command})
    if session.error:
        await websocket.send_json({"type": "exit", "data": session.error})

    async def pump() -> None:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)

    task = websocket.app.state.loop.create_task(pump())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                session.write(raw)
                continue
            mtype = msg.get("type", "input")
            if mtype == "input":
                session.write(msg.get("data", ""))
            elif mtype == "resize":
                try:
                    session.resize(
                        max(2, min(200, int(msg.get("rows", 24)))),
                        max(2, min(200, int(msg.get("cols", 80)))),
                    )
                except (TypeError, ValueError):
                    pass
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        session.detach(queue)
        if session.alive:
            session.close()
        terminal_manager.remove(session.id)
