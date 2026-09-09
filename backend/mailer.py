"""邮件服务：SMTP 配置存储、校验与发送。

配置保存在 ``data/email.json``，供 WebUI 系统通知与可视化插件共用。
密码在接口返回时统一使用 ``PASSWORD_MASK`` 掩码，提交掩码表示保留原密码。
"""

from __future__ import annotations

import asyncio
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Optional

from . import config
from .storage import load_json, save_json


EMAIL_FILE = config.EMAIL_FILE

# 接口返回密码时使用的掩码；提交该值表示不修改已保存的密码
PASSWORD_MASK = "******"

SECURITY_MODES = ("ssl", "starttls", "none")

DEFAULT_EMAIL_CONFIG: dict[str, Any] = {
    "enabled": False,
    "host": "",
    "port": 465,
    "security": "ssl",
    "username": "",
    "password": "",
    "from_addr": "",
    "from_name": "NoneBot2 WebUI",
    "recipients": [],
    "timeout": 15,
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.RLock()


class EmailError(Exception):
    """邮件配置或发送错误。"""


def _split_recipients(value: Any) -> list[str]:
    """把字符串（逗号/分号/空白分隔）或列表规范化为邮箱列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            parts.extend(re.split(r"[,;\s]+", str(item)))
    else:
        return []
    return [p.strip() for p in parts if p.strip()]


def _normalize(raw: dict) -> dict:
    """合并默认值并规范化字段类型，不做过多的业务校验。"""
    cfg = dict(DEFAULT_EMAIL_CONFIG)
    for key in DEFAULT_EMAIL_CONFIG:
        if key in raw and raw[key] is not None:
            cfg[key] = raw[key]

    cfg["enabled"] = bool(cfg["enabled"])
    cfg["host"] = str(cfg["host"] or "").strip()
    cfg["username"] = str(cfg["username"] or "").strip()
    cfg["password"] = str(cfg["password"] or "")
    cfg["from_addr"] = str(cfg["from_addr"] or "").strip()
    cfg["from_name"] = str(cfg["from_name"] or "").strip() or "NoneBot2 WebUI"

    try:
        port = int(cfg["port"])
    except (TypeError, ValueError):
        port = DEFAULT_EMAIL_CONFIG["port"]
    cfg["port"] = port if 1 <= port <= 65535 else DEFAULT_EMAIL_CONFIG["port"]

    security = str(cfg["security"] or "ssl").strip().lower()
    cfg["security"] = security if security in SECURITY_MODES else "ssl"

    try:
        timeout = int(cfg["timeout"])
    except (TypeError, ValueError):
        timeout = DEFAULT_EMAIL_CONFIG["timeout"]
    cfg["timeout"] = max(3, min(120, timeout))

    cfg["recipients"] = _split_recipients(cfg.get("recipients"))
    return cfg


def _validate(cfg: dict) -> None:
    if cfg["enabled"] and not cfg["host"]:
        raise EmailError("启用邮件通知前请先填写 SMTP 服务器地址")
    if cfg["enabled"] and not cfg["recipients"]:
        raise EmailError("启用邮件通知时请至少填写一个收件邮箱")
    if cfg["host"] and not (cfg["from_addr"] or cfg["username"]):
        raise EmailError("请填写发件人地址或 SMTP 用户名")
    if cfg["from_addr"] and not _EMAIL_RE.match(cfg["from_addr"]):
        raise EmailError(f"发件人地址格式不正确：{cfg['from_addr']}")
    for addr in cfg["recipients"]:
        if not _EMAIL_RE.match(addr):
            raise EmailError(f"收件邮箱格式不正确：{addr}")


def get_email_config() -> dict:
    """读取完整配置（含明文密码），仅供后端内部使用。"""
    with _lock:
        raw = load_json(EMAIL_FILE, {}) or {}
        if not isinstance(raw, dict):
            raw = {}
        return _normalize(raw)


def get_public_email_config() -> dict:
    """读取用于接口返回的配置：密码替换为掩码，并附带 password_set 标记。"""
    cfg = get_email_config()
    result = dict(cfg)
    result["password_set"] = bool(cfg["password"])
    result["password"] = PASSWORD_MASK if cfg["password"] else ""
    return result


def _merge_override(override: Optional[dict]) -> dict:
    """把前端提交的临时配置合并到已保存配置上，处理密码掩码。"""
    current = get_email_config()
    if not override:
        return current
    data = {k: v for k, v in override.items() if k in DEFAULT_EMAIL_CONFIG}
    if "password" in data and (data["password"] is None or data["password"] == PASSWORD_MASK):
        data["password"] = current["password"]
    return _normalize({**current, **data})


def save_email_config(data: dict) -> dict:
    """保存配置并返回掩码后的结果。"""
    with _lock:
        current = get_email_config()
        incoming = {k: v for k, v in (data or {}).items() if k in DEFAULT_EMAIL_CONFIG}
        if "password" in incoming and (
            incoming["password"] is None or incoming["password"] == PASSWORD_MASK
        ):
            incoming["password"] = current["password"]
        cfg = _normalize({**current, **incoming})
        _validate(cfg)
        save_json(EMAIL_FILE, cfg)
    return get_public_email_config()


def notifications_enabled() -> bool:
    """系统通知是否具备发送条件（启用 + 服务器 + 收件人）。"""
    cfg = get_email_config()
    return bool(cfg["enabled"] and cfg["host"] and cfg["recipients"])


def _build_message(cfg: dict, subject: str, body: str, to_list: list[str], html: bool) -> EmailMessage:
    from_addr = cfg["from_addr"] or cfg["username"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], from_addr))
    msg["To"] = ", ".join(to_list)
    if html:
        text = re.sub(r"<[^>]+>", "", body) or body
        msg.set_content(text)
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    return msg


def _connect_and_send(cfg: dict, msg: EmailMessage) -> None:
    host = cfg["host"]
    port = cfg["port"]
    timeout = cfg["timeout"]
    security = cfg["security"]
    try:
        if security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                host, port, timeout=timeout, context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        with server:
            if security == "starttls":
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if cfg["username"]:
                server.login(cfg["username"], cfg["password"])
            server.send_message(msg)
    except smtplib.SMTPException as exc:
        raise EmailError(f"SMTP 发送失败：{exc}") from exc
    except OSError as exc:
        raise EmailError(f"无法连接 SMTP 服务器：{exc}") from exc


def send_email_sync(
    subject: str,
    body: str,
    to: Any = None,
    html: bool = False,
    config_override: Optional[dict] = None,
) -> list[str]:
    """同步发送邮件，返回实际收件人列表。适合在线程/后台任务中调用。"""
    cfg = _merge_override(config_override)
    to_list = _split_recipients(to) or cfg["recipients"]
    if not cfg["host"]:
        raise EmailError("未配置 SMTP 服务器，请先在系统设置中配置邮件服务")
    if not (cfg["from_addr"] or cfg["username"]):
        raise EmailError("未配置发件人地址")
    if not to_list:
        raise EmailError("未配置收件邮箱")
    for addr in to_list:
        if not _EMAIL_RE.match(addr):
            raise EmailError(f"收件邮箱格式不正确：{addr}")
    msg = _build_message(cfg, subject, body, to_list, html)
    _connect_and_send(cfg, msg)
    return to_list


async def send_email(
    subject: str,
    body: str,
    to: Any = None,
    html: bool = False,
    config_override: Optional[dict] = None,
) -> list[str]:
    """异步发送邮件（内部用线程执行阻塞的 SMTP 操作）。"""
    return await asyncio.to_thread(
        send_email_sync, subject, body, to, html, config_override
    )


def test_email(config_override: Optional[dict] = None, to: Any = None) -> list[str]:
    """发送测试邮件，返回实际收件人列表。"""
    cfg = _merge_override(config_override)
    to_list = _split_recipients(to) or cfg["recipients"]
    if not to_list:
        raise EmailError("请先填写收件邮箱")
    subject = "NoneBot2 WebUI 邮件配置测试"
    body = (
        "这是一封来自 NoneBot2 WebUI 的测试邮件。\n\n"
        "如果你收到这封邮件，说明 SMTP 配置可用，系统通知与可视化插件的"
        "「发送邮件」组件都可以正常发信。"
    )
    return send_email_sync(
        subject, body, to_list, html=False, config_override=config_override
    )
