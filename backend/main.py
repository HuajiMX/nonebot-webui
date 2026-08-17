"""NoneBot2 WebUI 后端入口。"""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .bot_manager import bot_manager
from .config import FRONTEND_DIST, ensure_data_dir
from .process_manager import process_manager
from .routers import auth, bots, logs, monitor, plugins, terminal, update, visual_plugins
from .terminal import terminal_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dir()
    loop = asyncio.get_running_loop()
    app.state.loop = loop
    process_manager.set_loop(loop)
    # 清理上次服务退出后残留的机器人子进程，避免孤儿进程占用端口
    for bot in bot_manager.list_bots():
        if bot.status in ("running", "starting", "stopping") and bot.pid:
            try:
                os.kill(bot.pid, signal.SIGTERM)
            except OSError:
                pass
        bot.status = "stopped"
        bot.pid = None
        bot_manager.update_bot(bot)
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
    allow_origins=["*"],
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
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
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
