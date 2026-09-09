"""系统通知：机器人断连、异常退出等事件通过邮件通知管理员。

通知在后台线程发送，调用方（如日志读取线程）不会被 SMTP 阻塞；
同类事件带冷却时间，避免重连日志造成邮件轰炸。
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime
from typing import Optional

from . import mailer
from .bot_manager import bot_manager


logger = logging.getLogger(__name__)

# 同一机器人同类事件的邮件冷却时间（秒）
DEFAULT_COOLDOWN = 300.0

# 常见 OneBot / NoneBot 断连日志特征
DISCONNECT_RE = re.compile(
    r"(?:websocket|\bws\b|连接|链接|connection|socket)[^\n]{0,32}"
    r"(?:closed|close|disconnect|断开|关闭|丢失|重置|reset|lost|超时|timeout)"
    r"|已断开|失去连接|断线|连接已关闭|连接中断",
    re.IGNORECASE,
)

_lock = threading.RLock()
_last_sent: dict[str, float] = {}


def _should_send(key: str, cooldown: float = DEFAULT_COOLDOWN) -> bool:
    now = time.time()
    with _lock:
        last = _last_sent.get(key, 0.0)
        if now - last < cooldown:
            return False
        _last_sent[key] = now
        return True


def _dispatch(subject: str, body: str) -> None:
    """后台线程发送邮件，避免阻塞调用方。"""

    def _run() -> None:
        try:
            if not mailer.notifications_enabled():
                return
            mailer.send_email_sync(subject, body)
            logger.info("已发送系统通知邮件：%s", subject)
        except Exception as exc:  # noqa: BLE001
            logger.warning("发送系统通知邮件失败：%s", exc)

    threading.Thread(
        target=_run, daemon=True, name="webui-notify-mail"
    ).start()


def _bot_label(bot_id: str) -> tuple[str, Optional[str]]:
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        return bot_id, None
    return bot.name, bot.directory


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def notify_qq_disconnect(bot_id: str, detail: str = "") -> None:
    """检测到 QQ/协议端连接断开时发送通知。"""
    if not _should_send(f"disconnect:{bot_id}"):
        return
    name, directory = _bot_label(bot_id)
    subject = f"[NoneBot2 WebUI] 机器人「{name}」连接断开"
    body = (
        f"检测到机器人「{name}」与 QQ / 协议端的连接可能已断开。\n\n"
        f"时间：{_timestamp()}\n"
        f"机器人：{name}\n"
        f"机器人 ID：{bot_id}\n"
        f"目录：{directory or '-'}\n"
        f"日志片段：{detail or '-'}\n\n"
        "请检查协议端（如 NapCat）运行状态与网络连接，必要时在 WebUI 中重启机器人。"
    )
    _dispatch(subject, body)


def notify_bot_exit(bot_id: str, exit_code: Optional[int], detail: str = "") -> None:
    """机器人进程异常退出（非用户主动停止）时发送通知。"""
    if not _should_send(f"exit:{bot_id}"):
        return
    name, directory = _bot_label(bot_id)
    subject = f"[NoneBot2 WebUI] 机器人「{name}」进程已退出"
    body = (
        f"机器人「{name}」的进程已退出。\n\n"
        f"时间：{_timestamp()}\n"
        f"机器人：{name}\n"
        f"机器人 ID：{bot_id}\n"
        f"目录：{directory or '-'}\n"
        f"退出码：{exit_code if exit_code is not None else '-'}\n"
        f"说明：{detail or '进程异常退出'}\n\n"
        "可前往 WebUI 机器人详情页查看日志并重新启动。"
    )
    _dispatch(subject, body)
