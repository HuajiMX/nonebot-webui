"""更新检查与一键更新接口。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends

from .. import config
from ..deps import current_user
from ..version_check import check_update


router = APIRouter(prefix="/api/update", tags=["update"])


def _server_port() -> int:
    port = 9527
    if config.CONFIG_FILE.exists():
        try:
            cfg = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
            port = int(cfg.get("port", port))
        except (json.JSONDecodeError, ValueError, OSError):
            pass
    return port


@router.get("/status")
def update_status(_: str = Depends(current_user)) -> dict:
    return check_update()


@router.get("/log")
def update_log(_: str = Depends(current_user)) -> dict:
    """返回更新脚本的实时日志（供前端展示更新进度）。"""
    log_file = config.DATA_DIR / "update.log"
    text = ""
    if log_file.exists():
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    tail = "\n".join(lines[-3:])
    if "更新失败" in tail:
        state = "failed"
    elif "更新完成" in tail:
        state = "done"
    else:
        state = "running"
    return {"lines": lines[-500:], "state": state}


@router.post("")
def trigger_update(_: str = Depends(current_user)) -> dict:
    """启动独立更新脚本（下载 → 停止服务 → 替换代码 → 重启）。"""
    info = check_update(force=True)
    if not info.get("has_update"):
        return {"started": False, "detail": "当前已是最新版本"}
    download_url = info.get("download_url") or ""
    if not download_url:
        return {"started": False, "detail": "发布包缺少下载地址"}

    python = Path(sys.executable).resolve()
    update_script = config.PROJECT_ROOT / "update.py"
    log_file = config.DATA_DIR / "update.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(f"\n===== 开始更新 {info.get('latest')} @ {__import__('time').time()} =====\n")

    cmd = [
        str(python),
        str(update_script),
        "--url",
        download_url,
        "--port",
        str(_server_port()),
        "--pid",
        str(os.getpid()),
    ]
    creationflags = 0x08000000 if os.name == "nt" else 0
    log_handle = open(log_file, "a", encoding="utf-8")
    popen_kwargs = {}
    if os.name != "nt":
        # Linux/macOS 下让更新进程脱离当前会话，避免随 WebUI 进程组被连带结束
        popen_kwargs["start_new_session"] = True
    subprocess.Popen(
        cmd,
        cwd=str(config.PROJECT_ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
        **popen_kwargs,
    )
    log_handle.close()
    return {"started": True, "detail": f"更新已开始（v{info['latest']}），服务将自动重启"}
