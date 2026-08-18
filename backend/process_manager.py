"""机器人进程管理：启动/停止/重启、实时日志缓冲与 WebSocket 分发。"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional, Set

from .bot_manager import bot_manager


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class _BotProc:
    """单个机器人的运行进程与日志缓冲。"""

    def __init__(self, bot_id: str, proc: subprocess.Popen, manager: "ProcessManager") -> None:
        self.bot_id = bot_id
        self.proc = proc
        self.manager = manager
        self.stop_event = threading.Event()
        self.exit_code: Optional[int] = None
        self.stopped_by_user = False

    def feed(self, data: dict) -> None:
        self.manager._feed(self.bot_id, data)

    def reader(self) -> None:
        """读取子进程 stdout 并分发日志，进程退出后更新状态。"""
        assert self.proc.stdout is not None
        try:
            for raw in self.proc.stdout:
                line = raw.rstrip("\r\n")
                if line.strip() or self.stop_event.is_set():
                    self.feed({"type": "log", "data": line, "ts": time.time()})
        except Exception as exc:  # noqa: BLE001
            self.feed({"type": "log", "data": f"[WebUI] 读取日志出错：{exc}"})
        finally:
            self.proc.wait()
            self.exit_code = self.proc.returncode
            self.feed(
                {
                    "type": "exit",
                    "code": self.exit_code,
                    "ts": time.time(),
                    "data": (
                        f"[进程已退出，退出码 {self.exit_code}]"
                        if not self.stopped_by_user
                        else "[进程已停止]"
                    ),
                }
            )
            self.manager._on_exit(self)


class ProcessManager:
    """管理所有机器人子进程。"""

    def __init__(self) -> None:
        self._procs: Dict[str, _BotProc] = {}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._buffers: Dict[str, Deque[dict]] = {}
        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---------- 日志分发 ----------
    def _feed(self, bot_id: str, data: dict) -> None:
        """写入日志缓冲并广播（线程安全）。"""
        with self._lock:
            buf = self._buffers.setdefault(bot_id, deque(maxlen=2000))
            buf.append(data)
        self._emit(bot_id, data)

    def _emit(self, bot_id: str, data: dict) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._async_emit, bot_id, data)

    def _async_emit(self, bot_id: str, data: dict) -> None:
        subs = list(self._subscribers.get(bot_id, ()))
        for q in subs:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    def subscribe(self, bot_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(bot_id, set()).add(q)
        return q

    def unsubscribe(self, bot_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(bot_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subscribers.pop(bot_id, None)

    def recent_logs(self, bot_id: str) -> list[dict]:
        with self._lock:
            return list(self._buffers.get(bot_id, ()))

    def clear_logs(self, bot_id: str) -> None:
        with self._lock:
            self._buffers.pop(bot_id, None)

    # ---------- 进程生命周期 ----------
    def is_running(self, bot_id: str) -> bool:
        proc = self._procs.get(bot_id)
        return bool(proc and proc.proc.poll() is None)

    def get_pid(self, bot_id: str) -> Optional[int]:
        proc = self._procs.get(bot_id)
        return proc.proc.pid if proc else None

    def start(self, bot_id: str) -> None:
        """启动机器人。调用方需保证已停止或不存在。"""
        bot = bot_manager.get_bot(bot_id)
        if bot is None:
            raise ValueError("机器人不存在")
        bot_dir = bot.directory
        if not bot.python:
            raise ValueError("未配置 Python 解释器")
        python = bot.python

        # 入口文件兜底：已有项目缺少 bot.py 时，按 pyproject.toml 自动生成标准入口
        if not (Path(bot.directory) / "bot.py").exists():
            if not bot_manager.ensure_bot_entry(
                bot,
                log=lambda msg: self._feed(
                    bot_id, {"type": "log", "data": msg, "ts": time.time()}
                ),
            ):
                raise ValueError(
                    "机器人目录下未找到入口文件 bot.py，且无法自动生成"
                    "（需要 pyproject.toml 的 [tool.nonebot] 配置）"
                )
        # 已有项目：插件目录以项目 pyproject.toml 为准，修正历史注册遗留的默认值
        if not bot.managed:
            bot_manager.sync_plugin_dir(
                bot,
                log=lambda msg: self._feed(
                    bot_id, {"type": "log", "data": msg, "ts": time.time()}
                ),
            )

        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")

        creationflags = CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(
                [python, "bot.py"],
                cwd=bot_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001
            bot.status = "error"
            bot.extra["error"] = str(exc)
            bot_manager.update_bot(bot)
            raise RuntimeError(f"启动失败：{exc}") from exc

        bp = _BotProc(bot_id, proc, self)
        with self._lock:
            old = self._procs.get(bot_id)
            if old and old.proc.poll() is None:
                old.stopped_by_user = True
                self._terminate(old)
            self._procs[bot_id] = bp

        bot.status = "running"
        bot.pid = proc.pid
        bot.extra.pop("error", None)
        bot_manager.update_bot(bot)

        t = threading.Thread(target=bp.reader, daemon=True, name=f"bot-log-{bot.name}")
        t.start()

    def stop(self, bot_id: str, timeout: float = 8.0) -> None:
        bp = self._procs.get(bot_id)
        if not bp:
            bot = bot_manager.get_bot(bot_id)
            if bot:
                bot.status = "stopped"
                bot.pid = None
                bot_manager.update_bot(bot)
            return
        if bp.proc.poll() is None:
            bp.stopped_by_user = True
            self._terminate(bp)
        try:
            bp.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            bp.proc.kill()
            bp.proc.wait(timeout=5)

    def restart(self, bot_id: str) -> None:
        self.stop(bot_id)
        self.start(bot_id)

    def _terminate(self, bp: _BotProc) -> None:
        """尝试优雅停止子进程。"""
        try:
            if os.name == "nt":
                bp.proc.terminate()
            else:
                try:
                    os.killpg(os.getpgid(bp.proc.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    bp.proc.terminate()
        except OSError:
            pass

    def _on_exit(self, bp: _BotProc) -> None:
        with self._lock:
            if self._procs.get(bp.bot_id) is bp:
                self._procs.pop(bp.bot_id, None)
        bot = bot_manager.get_bot(bp.bot_id)
        if bot is None:
            return
        bot.pid = None
        if bp.stopped_by_user:
            bot.status = "stopped"
        else:
            bot.status = "error" if bp.exit_code not in (0, None) else "stopped"
            if bot.status == "error":
                bot.extra["error"] = f"进程异常退出，退出码 {bp.exit_code}"
        bot_manager.update_bot(bot)

    def shutdown_all(self) -> None:
        for bot_id in list(self._procs):
            try:
                self.stop(bot_id, timeout=3)
            except Exception:  # noqa: BLE001
                pass


# 全局单例
process_manager = ProcessManager()
