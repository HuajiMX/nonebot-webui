"""NoneBot2 WebUI 后端入口。"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import psutil

from . import __version__
from .bot_manager import bot_manager
from .config import FRONTEND_DIST, ensure_data_dir
from .process_manager import process_manager
from .routers import auth, bots, logs, monitor, plugins, terminal, update, visual_plugins
from .terminal import terminal_manager

logger = logging.getLogger(__name__)


def _is_managed_bot_process(pid: int, bot_dir: str) -> bool:
    """校验 PID 是否确为 WebUI 托管的机器人进程，避免 PID 复用误杀无关进程。"""
    try:
        proc = psutil.Process(pid)
        cmdline = proc.cmdline() or []
        if len(cmdline) < 2 or "bot.py" not in cmdline:
            return False
        try:
            return (
                str(proc.cwd()).lower()
                == str(Path(bot_dir).resolve()).lower()
            )
        except (psutil.AccessDenied, OSError):
            # 无法读取工作目录时，退化为仅校验命令行（机器人均由 WebUI 以 bot.py 拉起）
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dir()
    loop = asyncio.get_running_loop()
    app.state.loop = loop
    process_manager.set_loop(loop)
    # 清理上次服务退出后残留的机器人子进程，避免孤儿进程占用端口
    for bot in bot_manager.list_bots():
        if bot.status in ("running", "starting", "stopping") and bot.pid:
            if _is_managed_bot_process(bot.pid, bot.directory):
                try:
                    os.kill(bot.pid, signal.SIGTERM)
                except OSError:
                    pass
        bot.status = "stopped"
        bot.pid = None
        bot_manager.update_bot(bot)
    # 自动启动标记了 auto_start 的机器人（WebUI 每次启动时自动拉起）
    for bot in bot_manager.list_bots():
        if bot.auto_start:
            try:
                process_manager.start(bot.id)
                logger.info("已自动启动机器人：%s", bot.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("自动启动机器人「%s」失败：%s", bot.name, exc)
    yield
    process_manager.shutdown_all()
    terminal_manager.close_all()


app = FastAPI(
    title="NoneBot2 WebUI",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # 前端与 API 同源部署，跨源仅需覆盖本地开发/反代场景；
    # 不再使用通配符 + 凭据的组合，避免任意站点反射读取响应
    allow_origins=[
        "http://127.0.0.1",
        "http://localhost",
        "http://127.0.0.1:9527",
        "http://localhost:9527",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(bots.router)
app.include_router(plugins.router)
app.include_router(logs.router)
app.include_router(terminal.router)
app.include_router(monitor.router)
app.include_router(visual_plugins.router)
app.include_router(update.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


# 前端静态资源（构建后）
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="assets",
        )

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="前端未构建")
        return FileResponse(index)
else:
    @app.get("/")
    def root():
        return {"message": "NoneBot2 WebUI API 已启动", "docs": "/docs", "frontend": "前端未构建"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=9527, reload=False)
