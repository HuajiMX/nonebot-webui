"""内置终端：基于 PTY（Windows 使用 ConPTY/winpty，Unix 使用 pty）的会话管理。"""

from __future__ import annotations

import asyncio
import os
import platform
import threading
import time
import uuid
from typing import Dict, Optional

from .bot_manager import bot_manager


class TerminalSession:
    """一个 PTY 终端会话。"""

    def __init__(
        self,
        session_id: str,
        command: str,
        cwd: str,
        rows: int = 24,
        cols: int = 80,
        env: Optional[dict] = None,
    ) -> None:
        self.id = session_id
        self.command = command
        self.cwd = cwd
        self.rows = rows
        self.cols = cols
        self.pty = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subscribers: set[asyncio.Queue] = set()
        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = threading.Event()
        self.alive = False
        self.error: Optional[str] = None
        self.created_at = time.time()

        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        full_env.setdefault("PYTHONUTF8", "1")
        full_env.setdefault("TERM", "xterm-256color")

        if platform.system() == "Windows":
            self._spawn_windows(full_env)
        else:
            self._spawn_unix(full_env)

        if self.pty is not None:
            self.alive = True
            t = threading.Thread(target=self._reader, daemon=True, name=f"term-{session_id}")
            t.start()

    # ---------- 创建 ----------
    def _normalize_command(self) -> list:
        """将命令规范化为 argv 列表。

        pywinpty 对字符串命令会先用 shlex.split(posix=False) 解析，该模式会保留
        token 两侧的双引号，随后 list2cmdline 又对其再次转义，导致 cmd 把含引号
        的路径当作命令名执行（报“不是内部或外部命令”）。这里去掉整段包裹的
        双引号，交由 list2cmdline 统一处理带空格路径的引号。
        """
        import shlex

        if isinstance(self.command, str):
            argv = shlex.split(self.command, posix=False)
        else:
            argv = list(self.command)
        normalized = []
        for token in argv:
            if (
                len(token) >= 2
                and token[0] == token[-1] == '"'
                and '"' not in token[1:-1]
            ):
                token = token[1:-1]
            normalized.append(token)
        return normalized

    def _spawn_windows(self, env: dict) -> None:
        try:
            from winpty import PtyProcess

            argv = self._normalize_command()
            backend = None
            try:
                # 优先使用 ConPTY（对现代程序兼容性更好）
                import winpty.enums

                backend = winpty.enums.Backend.ConPTY
            except Exception:  # noqa: BLE001
                backend = None
            try:
                self.pty = PtyProcess.spawn(
                    argv,
                    cwd=self.cwd,
                    env=env,
                    dimensions=(self.rows, self.cols),
                    backend=backend,
                )
            except Exception:
                # ConPTY 失败时回退到 WinPTY
                self.pty = PtyProcess.spawn(
                    argv,
                    cwd=self.cwd,
                    env=env,
                    dimensions=(self.rows, self.cols),
                )
        except Exception as exc:  # noqa: BLE001
            self.error = f"终端启动失败：{exc}"

    def _spawn_unix(self, env: dict) -> None:
        try:
            import ptyprocess

            self.pty = ptyprocess.PtyProcess.spawn(
                ["bash", "-c", self.command],
                cwd=self.cwd,
                env=env,
                dimensions=(self.rows, self.cols),
            )
        except Exception as exc:  # noqa: BLE001
            self.error = f"终端启动失败：{exc}"

    # ---------- 读写 ----------
    def _reader(self) -> None:
        while not self._stop.is_set():
            try:
                data = self.pty.read(4096)
            except EOFError:
                self._push({"type": "exit", "data": "[会话已结束]"})
                break
            except Exception as exc:  # noqa: BLE001
                self._push({"type": "exit", "data": f"[终端错误] {exc}"})
                break
            if data:
                self._push({"type": "output", "data": data})
        self.alive = False
        self._push({"type": "exit", "data": ""})

    def _push(self, msg: dict) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._async_push, msg)

    def _async_push(self, msg: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    def attach(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        self._loop = loop
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subscribers.add(q)
        return q

    def detach(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def write(self, data: str) -> None:
        if self.pty is None:
            return
        try:
            if platform.system() == "Windows":
                # winpty 需要处理 \r 与特殊按键
                self.pty.write(data)
            else:
                self.pty.write(data)
        except Exception:  # noqa: BLE001
            pass

    def resize(self, rows: int, cols: int) -> None:
        if self.pty is None:
            return
        self.rows = max(2, rows)
        self.cols = max(2, cols)
        try:
            self.pty.setwinsize(self.rows, self.cols)
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        self._stop.set()
        try:
            if self.pty is not None:
                self.pty.close()
        except Exception:  # noqa: BLE001
            pass
        self.alive = False


class TerminalManager:
    """终端会话注册表。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, TerminalSession] = {}
        self._lock = threading.RLock()

    def create(
        self,
        command: str,
        cwd: str,
        rows: int = 24,
        cols: int = 80,
    ) -> TerminalSession:
        session_id = uuid.uuid4().hex[:16]
        session = TerminalSession(session_id, command, cwd, rows, cols)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[TerminalSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    def list(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": s.id,
                    "command": s.command,
                    "alive": s.alive,
                    "error": s.error,
                }
                for s in self._sessions.values()
            ]

    def close_all(self) -> None:
        for sid in list(self._sessions):
            self.remove(sid)


def bot_terminal_command(bot_id: str) -> tuple[list[str] | str, str]:
    """返回机器人内置 venv 终端命令与工作目录。

    Windows 返回参数列表（避免 pywinpty 字符串解析导致引号双重转义），
    Unix 返回 shell 命令字符串。
    """
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    cwd = bot.directory
    if platform.system() == "Windows":
        venv = bot.venv
        if venv:
            activate = os.path.join(venv, "Scripts", "activate.bat")
            if os.path.exists(activate):
                return ["cmd", "/k", activate], cwd
        return ["cmd", "/k", "chcp 65001 >nul"], cwd
    venv = bot.venv
    if venv:
        activate = os.path.join(venv, "bin", "activate")
        if os.path.exists(activate):
            return f'bash --rcfile "{activate}" -i', cwd
    return "bash -i", cwd


terminal_manager = TerminalManager()
