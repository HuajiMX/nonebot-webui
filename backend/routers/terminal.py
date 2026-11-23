"""内置终端接口（WebSocket）。

终端类型：
- ``bot``：机器人环境终端（在机器人目录中打开并激活其 venv）；
- ``system``：普通终端（服务所在主机的常规 shell，工作目录为用户主目录）。
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..deps import ws_auth
from ..terminal import bot_terminal_command, system_terminal_command, terminal_manager


router = APIRouter(prefix="/api/terminal", tags=["terminal"])


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await ws_auth(websocket)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="未认证")
        return

    terminal_type = websocket.query_params.get("type", "bot")
    if terminal_type not in ("bot", "system"):
        await websocket.close(code=4400, reason="不支持的终端类型")
        return

    command = ""
    if terminal_type == "bot":
        bot_id = websocket.query_params.get("bot_id", "")
        try:
            command, cwd = bot_terminal_command(bot_id)
        except ValueError:
            await websocket.close(code=4404, reason="机器人不存在")
            return
    else:
        command, cwd = system_terminal_command()

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
        # 启动失败（如 pty 依赖缺失）：告知前端并结束
        await websocket.send_json({"type": "exit", "data": session.error})
        await websocket.close(code=1011, reason="终端启动失败")
        await asyncio.to_thread(terminal_manager.remove, session.id)
        return

    async def pump() -> None:
        while True:
            msg = await queue.get()
            try:
                await websocket.send_json(msg)
            except Exception:  # noqa: BLE001
                # 发送失败（客户端已断开）时安静退出，绝不向上抛
                return

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
        # 会话销毁最终会调用 ptyprocess.PtyProcess.close()。只要 reader 线程还阻塞
        # 在该 pty 的 read() 上，close() 就会与内核 tty 释放流程互锁并永久挂起。
        # 若直接在事件循环里 await/调用它，唯一的 loop 线程会被卡死，导致全站接口
        # 超时（前端显示"网络错误，请检查服务是否启动"）。因此：
        #   ① close() 内部已改为"先杀子进程→等 reader 退出→最后关 master"；
        #   ② 这里再做一层隔离，把销毁放到工作线程执行，事件循环始终保持响应。
        await asyncio.to_thread(terminal_manager.remove, session.id)
