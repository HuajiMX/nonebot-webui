"""服务器运行状态监控（CPU/内存/磁盘/网络等）。"""

from __future__ import annotations

import os
import platform
import time
from typing import Optional

import psutil

from . import __version__
from .bot_manager import bot_manager


_last_net = {"time": 0.0, "bytes_sent": 0, "bytes_recv": 0}


def snapshot() -> dict:
    """采集一次系统状态快照。"""
    global _last_net

    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    try:
        disk = psutil.disk_usage("/" if os.name != "nt" else os.path.splitdrive(os.getcwd())[0] + "\\")
    except Exception:  # noqa: BLE001
        disk = None

    net = psutil.net_io_counters()
    now = time.time()
    elapsed = max(now - _last_net["time"], 0.001)
    up = (net.bytes_sent - _last_net["bytes_sent"]) / elapsed
    down = (net.bytes_recv - _last_net["bytes_recv"]) / elapsed
    _last_net = {"time": now, "bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv}

    boot = psutil.boot_time()
    procs = []
    try:
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: -(x.get("cpu_percent") or 0))
        procs = procs[:10]
    except Exception:  # noqa: BLE001
        procs = []

    bots = bot_manager.list_bots()
    running = sum(1 for b in bots if b.status == "running")

    return {
        "time": now,
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "webui_version": __version__,
        "uptime": int(now - boot),
        "cpu": {
            "percent": cpu_percent,
            "per_core": cpu_per_core,
            "count": psutil.cpu_count(),
        },
        "memory": {
            "total": mem.total,
            "used": mem.used,
            "available": mem.available,
            "percent": mem.percent,
        },
        "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        }
        if disk
        else None,
        "network": {"up": up, "down": down},
        "processes": procs,
        "bots": {"total": len(bots), "running": running},
    }
