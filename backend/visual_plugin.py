"""可视化插件：流程存储、校验与 NoneBot(OneBot V11) 插件代码生成。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from . import config
from .bot_manager import bot_manager
from .plugin_manager import install_plugin_file
from .storage import load_json, save_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


VISUAL_PLUGINS_FILE = config.DATA_DIR / "visual_plugins.json"


class VisualPlugin(BaseModel):
    id: str
    name: str
    description: str = ""
    module: str = ""  # 生成插件文件名（不含 .py）
    flow: Dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    installed: List[Dict[str, str]] = Field(default_factory=list)  # [{bot_id, installed_at}]
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# 组件目录（同时供前端编辑器使用）
# ---------------------------------------------------------------------------

NODE_CATALOG = {
    # ---- 监听对象 ----
    "listener_group": {
        "category": "listener",
        "label": "群聊监听",
        "default": {
            "listener_type": "group",
            "groups": "all",  # all 或逗号分隔群号
            "keywords": "",
            "match": "contains",  # contains | starts_with | regex
            "at_me": False,  # 仅当@我时触发
        },
    },
    "listener_private": {
        "category": "listener",
        "label": "私信监听",
        "default": {
            "listener_type": "private",
            "users": "all",  # all 或逗号分隔 QQ 号
            "keywords": "",
            "match": "contains",
        },
    },
    "listener_webhook": {
        "category": "listener",
        "label": "WebHook",
        "default": {"listener_type": "webhook", "path": "", "var": "webhook"},
    },
    # ---- 基本组件 ----
    "logic": {
        "category": "basic",
        "label": "条件判断",
        "default": {
            "combine": "and",
            "conditions": [{"left": "{{msg}}", "op": "contains", "right": ""}],
            "negate": False,
        },
    },
    "loop": {
        "category": "basic",
        "label": "循环遍历",
        "default": {"items": "", "var": "item", "end": ""},
    },
    "schedule": {
        "category": "listener",
        "label": "定时任务",
        "default": {"mode": "interval", "interval": 60, "time": "09:00", "weekday": 1, "day": 1},
    },
    "api": {
        "category": "feature",
        "label": "API请求",
        "default": {
            "method": "GET",
            "url": "",
            "headers": [],
            "body": "",
            "var": "api_resp",
            "timeout": 10,
        },
    },
    "send_email": {
        "category": "feature",
        "label": "发送邮件",
        "default": {
            "to": "",  # 留空=使用 WebUI 系统通知收件邮箱，多个用逗号分隔
            "subject": "来自 {{bot_name}} 的通知",
            "body": "",
            "html": False,
        },
    },
    "code": {
        "category": "basic",
        "label": "自定义代码",
        "default": {"code": ""},
    },
    # ---- 机器人动作 ----
    "send": {
        "category": "action",
        "label": "发送消息",
        "default": {
            "mode": "continue",  # finish | continue
            "target": {"type": "event", "id": ""},
            "messages": [{"type": "text", "value": ""}],
        },
    },
    # ---- 会话控制 ----
    "conversation_entry": {
        "category": "session",
        "label": "会话入口",
        "default": {"session": "", "end": ""},
    },
    "collect": {
        "category": "session",
        "label": "信息收集",
        "default": {"key": "reply", "prompt": ""},
    },
    "choice": {
        "category": "session",
        "label": "选项交互",
        "default": {"prompt": "", "options": ["选项一", "选项二"], "var": "choice"},
    },
    "loop_end": {
        "category": "session",
        "label": "循环结束",
        "hidden": True,
        "default": {"loop": ""},
    },
    "session_end": {
        "category": "session",
        "label": "会话结束",
        "hidden": True,
        "default": {"entry": ""},
    },
}

CONDITION_OPS = {
    "contains": "包含",
    "not_contains": "不包含",
    "equals": "等于",
    "not_equals": "不等于",
    "startswith": "以...开头",
    "endswith": "以...结尾",
    "regex": "正则匹配",
    "gt": "大于",
    "gte": "大于等于",
    "lt": "小于",
    "lte": "小于等于",
    "in": "属于(右值列表)",
    "not_in": "不属于(右值列表)",
    "is_empty": "为空",
    "not_empty": "不为空",
}

MESSAGE_TYPES = {
    "text": "文本",
    "image": "图片",
    "face": "QQ内置表情",
    "meme": "表情包(图片)",
    "at": "艾特",
    "record": "语音",
    "video": "视频",
}

# 生成代码中作为标识符使用的字段必须匹配该正则，防止流程数据注入任意 Python
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_ident(cfg: dict, key: str, node_id: str, default: str) -> str:
    """校验配置字段必须是合法 Python 标识符，返回规范化后的值。"""
    value = str(cfg.get(key) or "").strip() or default
    if not IDENT_RE.match(value):
        raise ValueError(f"节点 {node_id} 的「变量名」必须是合法 Python 变量名")
    return value


def _validate_node_config(ntype: str, cfg: dict, node_id: str) -> None:
    """按节点类型校验配置内容，防止生成代码注入与非法配置。"""
    if ntype == "loop":
        _require_ident(cfg, "var", node_id, "item")
    elif ntype == "collect":
        _require_ident(cfg, "key", node_id, "reply")
    elif ntype in ("api", "choice"):
        _require_ident(cfg, "var", node_id, "api_resp" if ntype == "api" else "choice")
    elif ntype == "listener_webhook":
        _require_ident(cfg, "var", node_id, "webhook")
        path = str(cfg.get("path") or "").strip()
        if path and not path.startswith("/"):
            raise ValueError(f"节点 {node_id} 的 WebHook 路径必须以 / 开头")
    elif ntype in ("listener_group", "listener_private"):
        field = "groups" if ntype == "listener_group" else "users"
        value = str(cfg.get(field) or "all").strip() or "all"
        if value != "all":
            parts = [x.strip() for x in value.split(",") if x.strip()]
            if not parts or any(not x.isdigit() for x in parts):
                raise ValueError(
                    f"节点 {node_id} 的「{'群号' if ntype == 'listener_group' else 'QQ 号'}」"
                    "必须是逗号分隔的数字或 all"
                )
        keywords = cfg.get("keywords") or ""
        if isinstance(keywords, str):
            for kw in keywords.split(","):
                if len(kw.strip()) > 200:
                    raise ValueError(f"节点 {node_id} 的触发关键词过长（单个不超过 200 字符）")


# ---------------------------------------------------------------------------
# 流程校验与迁移
# ---------------------------------------------------------------------------

def _validate_flow(flow: dict, require_entry: bool = True) -> None:
    nodes = flow.get("nodes") or []
    edges = flow.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("流程数据格式错误")
    ids: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n or "type" not in n:
            raise ValueError("节点数据格式错误")
        if n["id"] in ids:
            raise ValueError(f"节点 id 重复：{n['id']}")
        ids.add(n["id"])
        if n["type"] not in NODE_CATALOG:
            raise ValueError(f"未知节点类型：{n['type']}")
        cfg = n.get("config")
        if not isinstance(cfg, dict):
            raise ValueError(f"节点 {n['id']} 配置格式错误")
        _validate_node_config(n["type"], cfg, n["id"])
    for e in edges:
        if e.get("from") not in ids or e.get("to") not in ids:
            raise ValueError("连线引用了不存在的节点")
        port = e.get("port")
        if port not in ("next", "true", "false") and not (
            isinstance(port, str) and port.startswith("opt_")
        ):
            raise ValueError("未知连线端口")
    if not require_entry:
        return
    has_entry = any(
        n["type"] in ("listener_group", "listener_private", "listener_webhook", "schedule")
        for n in nodes
    )
    if not has_entry:
        raise ValueError("流程至少需要一个监听对象或定时任务节点")
    if not nodes:
        raise ValueError("流程为空")


def _migrate_flow(flow: dict) -> dict:
    """兼容旧版本流程：简单条件判断 / 会话分支 合并为「条件判断」(logic)。"""
    nodes = []
    for n in flow.get("nodes") or []:
        node = dict(n)
        ntype = node.get("type")
        if ntype in ("condition", "branch"):
            cfg = dict(node.get("config") or {})
            node = {
                **node,
                "type": "logic",
                "config": {
                    "combine": "and",
                    "conditions": [
                        {
                            "left": cfg.get("left", ""),
                            "op": cfg.get("op", "contains"),
                            "right": cfg.get("right", ""),
                        }
                    ],
                    "negate": False,
                },
            }
        nodes.append(node)
    return {"nodes": nodes, "edges": flow.get("edges") or []}


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------

def list_visual_plugins() -> List[dict]:
    raw = load_json(VISUAL_PLUGINS_FILE, []) or []
    bots = {b.id: b for b in bot_manager.list_bots()}
    result = []
    for item in raw:
        item = dict(item)
        item["flow"] = _migrate_flow(item.get("flow") or {"nodes": [], "edges": []})
        plugin = VisualPlugin(**item)
        installed = []
        for entry in plugin.installed:
            bot = bots.get(entry.get("bot_id", ""))
            installed.append(
                {
                    "bot_id": entry.get("bot_id", ""),
                    "bot_name": bot.name if bot else entry.get("bot_id", ""),
                    "installed_at": entry.get("installed_at", ""),
                }
            )
        result.append(
            {
                **plugin.model_dump(),
                "installed": installed,
                "node_count": len(plugin.flow.get("nodes") or []),
            }
        )
    return result


def get_visual_plugin(plugin_id: str) -> Optional[VisualPlugin]:
    for item in list_visual_plugins():
        if item["id"] == plugin_id:
            data = {k: v for k, v in item.items() if k not in ("node_count",)}
            data["installed"] = [
                {
                    "bot_id": entry.get("bot_id", ""),
                    "installed_at": entry.get("installed_at", ""),
                }
                for entry in (data.get("installed") or [])
            ]
            return VisualPlugin(**data)
    return None


def _save_all(plugins: List[VisualPlugin]) -> None:
    save_json(VISUAL_PLUGINS_FILE, [p.model_dump() for p in plugins])


def create_visual_plugin(name: str, description: str = "") -> VisualPlugin:
    name = name.strip()
    if not name:
        raise ValueError("插件名称不能为空")
    if len(name) > 64:
        raise ValueError("插件名称过长")
    plugins = [VisualPlugin(**p) for p in list_visual_plugins()]
    if any(p.name == name for p in plugins):
        raise ValueError("已存在同名可视化插件")
    plugin = VisualPlugin(
        id=uuid.uuid4().hex[:12],
        name=name,
        description=description.strip(),
        module=f"vplugin_{uuid.uuid4().hex[:10]}",
        flow={"nodes": [], "edges": []},
        created_at=_now(),
        updated_at=_now(),
    )
    plugins.append(plugin)
    _save_all(plugins)
    return plugin


def update_visual_plugin(plugin_id: str, name: str, description: str, flow: dict) -> VisualPlugin:
    plugins = [VisualPlugin(**p) for p in list_visual_plugins()]
    target = next((p for p in plugins if p.id == plugin_id), None)
    if target is None:
        raise KeyError(plugin_id)
    name = name.strip()
    if not name:
        raise ValueError("插件名称不能为空")
    if any(p.name == name and p.id != plugin_id for p in plugins):
        raise ValueError("已存在同名可视化插件")
    _validate_flow(flow, require_entry=False)
    target.name = name
    target.description = description.strip()
    target.flow = flow
    target.updated_at = _now()
    _save_all(plugins)
    return target


def delete_visual_plugin(plugin_id: str) -> None:
    plugins = [VisualPlugin(**p) for p in list_visual_plugins()]
    target = next((p for p in plugins if p.id == plugin_id), None)
    if target is None:
        raise KeyError(plugin_id)
    for entry in list(target.installed):
        try:
            uninstall_from_bot(plugin_id, entry["bot_id"])
        except Exception:  # noqa: BLE001
            pass
    _save_all([p for p in plugins if p.id != plugin_id])


# ---------------------------------------------------------------------------
# 代码生成（编译为直接控制流，非运行时解释）
# ---------------------------------------------------------------------------

_RUNTIME_TEMPLATE = '''\
# 由 NoneBot2 WebUI 可视化插件生成（OneBot V11）
# 插件名：%%PLUGIN_NAME%%

from __future__ import annotations

import asyncio
import calendar
import datetime
import json
import os
import re
import smtplib
import ssl
import subprocess
import time
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, Optional

import httpx
import nonebot
from nonebot import Bot, get_driver, on_message
from nonebot.adapters import Event
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)

try:
    import psutil  # 可选依赖，用于系统信息
except Exception:  # noqa: BLE001
    psutil = None

PLUGIN_NAME = %%PLUGIN_NAME%%
PLUGIN_MODULE = %%PLUGIN_MODULE%%
BOT_NAME = %%BOT_NAME%%
_EMAIL_CONFIG_PATH = %%EMAIL_CONFIG_PATH%%

_sessions: Dict[str, dict] = {}
_pending: Dict[str, dict] = {}
_bg_tasks: set = set()


def _spawn(coro) -> None:
    """启动后台任务并持有引用，避免任务被垃圾回收。"""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


_SAFE_BUILTINS = {
    "range": range,
    "list": list,
    "tuple": tuple,
    "len": len,
    "int": int,
    "str": str,
    "float": float,
    "dict": dict,
    "set": set,
}


def _resolve(ctx: dict, name: str) -> Any:
    """按点路径从上下文中取值，支持 segments.0.type 形式。"""
    obj: Any = ctx
    for part in name.replace("[", ".").replace("]", "").split("."):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, (list, tuple)) and part.isdigit():
            try:
                obj = obj[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            obj = getattr(obj, part, None)
    return obj


_VAR_RE = re.compile(r"\\{\\{\\s*([A-Za-z_][\\w.\\[\\]0-9]*)\\s*\\}\\}")


def _tpl(s: Any, ctx: dict) -> Any:
    """把字符串中的 {{变量}} 替换为上下文值。"""
    if not isinstance(s, str):
        return s

    def _rep(m: re.Match) -> str:
        v = _resolve(ctx, m.group(1))
        return "" if v is None else str(v)

    return _VAR_RE.sub(_rep, s)


def _value(expr: Any, ctx: dict) -> Any:
    """条件表达式的取值：{{变量}} 取变量；其余按模板替换后返回字符串。"""
    expr = str(expr).strip()
    if expr.startswith("{{") and expr.endswith("}}"):
        return _resolve(ctx, expr[2:-2].strip())
    return _tpl(expr, ctx)


def _num(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _eval_one(cond: dict, ctx: dict) -> bool:
    left = _value(cond.get("left", ""), ctx)
    right = _value(cond.get("right", ""), ctx)
    op = cond.get("op", "contains")
    if op == "is_empty":
        return _is_empty(left)
    if op == "not_empty":
        return not _is_empty(left)
    if op == "contains":
        return str(right) in str(left)
    if op == "not_contains":
        return str(right) not in str(left)
    if op == "equals":
        return str(left) == str(right)
    if op == "not_equals":
        return str(left) != str(right)
    if op == "startswith":
        return str(left).startswith(str(right))
    if op == "endswith":
        return str(left).endswith(str(right))
    if op == "regex":
        try:
            return re.search(str(right), str(left)) is not None
        except re.error:
            return False
    if op == "in":
        return str(left) in [x.strip() for x in str(right).split(",") if x.strip()]
    if op == "not_in":
        return str(left) not in [x.strip() for x in str(right).split(",") if x.strip()]
    if op in ("gt", "gte", "lt", "lte"):
        a, b = _num(left), _num(right)
        if a is None or b is None:
            return False
        return {
            "gt": lambda: a > b,
            "gte": lambda: a >= b,
            "lt": lambda: a < b,
            "lte": lambda: a <= b,
        }[op]()
    return False


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, tuple, dict, set)):
        return len(v) == 0
    return False


def _eval_logic(cfg: dict, ctx: dict) -> bool:
    conds = cfg.get("conditions") or []
    if not conds:
        return bool(cfg.get("negate"))
    results = [_eval_one(c, ctx) for c in conds]
    ok = all(results) if cfg.get("combine", "and") == "and" else any(results)
    if cfg.get("negate"):
        ok = not ok
    return ok


def _system_info() -> dict:
    info: dict = {}
    try:
        if psutil is not None:
            info["cpu"] = psutil.cpu_percent(interval=None)
            info["memory"] = psutil.virtual_memory().percent
            try:
                info["disk"] = psutil.disk_usage("/").percent
            except Exception:  # noqa: BLE001
                pass
            if hasattr(os, "getloadavg"):
                try:
                    info["load"] = list(os.getloadavg())
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    info["gpu"] = _gpu_info()
    return info


def _gpu_info() -> dict:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        line = (proc.stdout or "").strip().splitlines()
        if line and "," in line[0]:
            util, mem_used, mem_total = [x.strip() for x in line[0].split(",")]
            return {"utilization": float(util), "memory_used": float(mem_used), "memory_total": float(mem_total)}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _load_email_config() -> dict:
    """读取 WebUI 的邮件配置：环境变量指定的路径优先，其次生成时嵌入的路径。"""
    path = os.environ.get("NB_WEBUI_EMAIL_CONFIG") or _EMAIL_CONFIG_PATH
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _email_recipients(raw: Any, cfg: dict) -> list:
    """解析收件人：节点配置优先，为空时回退到 WebUI 系统通知收件邮箱。"""
    items: list = []
    if isinstance(raw, str):
        items = [x.strip() for x in re.split(r"[,;\\s]+", raw) if x.strip()]
    elif isinstance(raw, (list, tuple)):
        for x in raw:
            items.extend(y.strip() for y in re.split(r"[,;\\s]+", str(x)) if y.strip())
    if not items:
        rec = cfg.get("recipients") or []
        if isinstance(rec, str):
            rec = [x.strip() for x in re.split(r"[,;\\s]+", rec) if x.strip()]
        items = [str(x).strip() for x in rec if str(x).strip()]
    return items


def _send_email_sync(to_list: list, subject: str, body: str, html: bool) -> None:
    cfg = _load_email_config()
    host = str(cfg.get("host") or "").strip()
    if not host:
        raise RuntimeError("未配置 SMTP 服务器，请先在 WebUI 系统设置中配置邮件服务")
    try:
        port = int(cfg.get("port") or 465)
    except (TypeError, ValueError):
        port = 465
    security = str(cfg.get("security") or "ssl").lower()
    try:
        timeout = float(cfg.get("timeout") or 15)
    except (TypeError, ValueError):
        timeout = 15.0
    username = str(cfg.get("username") or "")
    password = str(cfg.get("password") or "")
    from_addr = str(cfg.get("from_addr") or "").strip() or username
    if not from_addr:
        raise RuntimeError("未配置发件人地址，请先在 WebUI 系统设置中完善邮件配置")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((str(cfg.get("from_name") or "NoneBot2 WebUI"), from_addr))
    msg["To"] = ", ".join(to_list)
    if html:
        msg.set_content(re.sub(r"<[^>]+>", "", body) or body)
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
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
        if username:
            server.login(username, password)
        server.send_message(msg)


async def _send_email(ctx: dict, to: Any, subject: Any, body: Any, html: Any = False) -> None:
    """发送邮件（使用 WebUI 设置中的 SMTP 配置），结果写入 ctx 的 email_sent/email_result。"""
    cfg = _load_email_config()
    to_list = _email_recipients(_tpl(to, ctx), cfg)
    subject_text = str(_tpl(subject, ctx) or "NoneBot2 WebUI 通知")
    body_text = str(_tpl(body, ctx) or "")
    if not to_list:
        ctx["email_sent"] = False
        ctx["email_result"] = {"ok": False, "error": "未配置收件人"}
        nonebot.logger.warning("[可视化插件] 发送邮件失败：未配置收件人")
        return
    try:
        await asyncio.to_thread(_send_email_sync, to_list, subject_text, body_text, bool(html))
        ctx["email_sent"] = True
        ctx["email_result"] = {"ok": True, "to": to_list, "subject": subject_text}
    except Exception as exc:  # noqa: BLE001
        ctx["email_sent"] = False
        ctx["email_result"] = {
            "ok": False,
            "to": to_list,
            "subject": subject_text,
            "error": str(exc),
        }
        nonebot.logger.warning(f"[可视化插件] 发送邮件失败：{exc}")


def _build_ctx(bot: Optional[Bot], event: Optional[Event], webhook: Optional[dict] = None) -> dict:
    ctx: dict = {"event": event, "bot": bot}
    if event is not None:
        message = getattr(event, "message", None)
        ctx["msg"] = message.extract_plain_text() if message is not None else ""
        ctx["raw_msg"] = getattr(event, "raw_message", "")
        ctx["segments"] = (
            [{"type": s.type, "data": dict(s.data)} for s in message] if message is not None else []
        )
        ctx["user_id"] = getattr(event, "user_id", None)
        ctx["group_id"] = getattr(event, "group_id", None)
        sender = getattr(event, "sender", None)
        if sender is not None:
            ctx["sender"] = {
                "user_id": getattr(sender, "user_id", None),
                "nickname": getattr(sender, "card", None) or getattr(sender, "nickname", None) or "",
                "card": getattr(sender, "card", None) or "",
            }
        else:
            ctx["sender"] = {}
    else:
        ctx.update(
            msg="", raw_msg="", segments=[], user_id=None, group_id=None, sender={}
        )
    ctx["bot_id"] = bot.self_id if bot is not None else ""
    ctx["bot_name"] = BOT_NAME
    ctx["system"] = _system_info()
    ctx["reply"] = None
    ctx["webhook"] = webhook or {}
    return ctx


def _session_key(event: Optional[Event]) -> str:
    if event is None:
        return "webhook"
    try:
        return event.get_session_id()
    except Exception:  # noqa: BLE001
        return "unknown"


def _build_message(msgs: list, ctx: dict) -> Message:
    out = Message()
    for seg in msgs or []:
        t = seg.get("type", "text")
        v = _tpl(seg.get("value", ""), ctx)
        if t == "text":
            out += MessageSegment.text(v)
        elif t == "image":
            out += MessageSegment.image(v)
        elif t == "face":
            try:
                out += MessageSegment.face(int(v or 0))
            except (TypeError, ValueError):
                pass
        elif t == "meme":
            out += MessageSegment.image(v)
        elif t == "at":
            target = str(v) if str(v).isdigit() else str(ctx.get("user_id") or 0)
            try:
                out += MessageSegment.at(int(target))
            except (TypeError, ValueError):
                pass
        elif t == "record":
            out += MessageSegment.record(v)
        elif t == "video":
            out += MessageSegment.video(v)
    return out


def _resolve_bot(ctx: dict) -> Optional[Bot]:
    """解析可用的 Bot 对象。

    消息监听触发时直接用上下文里的 Bot；定时任务 / WebHook 触发没有事件，
    因此从 NoneBot 当前的连接池中取（指定了 bot_id 则精确匹配，否则取第一个）。
    """
    bot = ctx.get("bot")
    if bot is not None:
        return bot
    try:
        bots = nonebot.get_bots()
    except Exception:  # noqa: BLE001
        return None
    if not bots:
        return None
    bot_id = str(ctx.get("bot_id") or "")
    if bot_id and bot_id in bots:
        return bots[bot_id]
    return next(iter(bots.values()))


def _attach_bot(ctx: dict) -> None:
    """给没有事件的触发分支（定时任务 / WebHook）补齐 Bot 与 bot_id。"""
    bot = _resolve_bot(ctx)
    if bot is not None:
        ctx["bot"] = bot
        ctx["bot_id"] = bot.self_id


async def _send(ctx: dict, msgs: list, target_cfg: Optional[dict] = None) -> None:
    event = ctx.get("event")
    target_cfg = target_cfg or {}
    target = target_cfg.get("type", "event")
    message = _build_message(msgs, ctx)
    if not message:
        nonebot.logger.warning("[可视化插件] 发送消息失败：消息内容为空")
        return
    bot = _resolve_bot(ctx)
    if bot is None:
        nonebot.logger.warning("[可视化插件] 发送消息失败：当前没有已连接的机器人")
        return
    if target == "event" and event is None:
        nonebot.logger.warning(
            "[可视化插件] 发送消息失败：定时任务 / WebHook 触发没有消息来源，"
            "请在发送节点选择「指定群聊」或「指定私聊」"
        )
        return
    try:
        if target == "group":
            gid = int(target_cfg.get("id") or ctx.get("group_id") or 0)
            if gid:
                await bot.call_api("send_group_msg", group_id=gid, message=message)
            else:
                nonebot.logger.warning("[可视化插件] 发送消息失败：未指定群号")
        elif target == "user":
            uid = int(target_cfg.get("id") or ctx.get("user_id") or 0)
            if uid:
                await bot.call_api("send_private_msg", user_id=uid, message=message)
            else:
                nonebot.logger.warning("[可视化插件] 发送消息失败：未指定 QQ 号")
        elif event is not None:
            await bot.send(event, message)
    except Exception as exc:  # noqa: BLE001
        nonebot.logger.warning(f"[可视化插件] 发送消息失败：{exc}")


def _code_scope(ctx: dict) -> dict:
    return {
        "ctx": ctx,
        "msg": ctx.get("msg"),
        "segments": ctx.get("segments"),
        "sender": ctx.get("sender"),
        "user_id": ctx.get("user_id"),
        "group_id": ctx.get("group_id"),
        "event": ctx.get("event"),
        "bot": ctx.get("bot"),
        "system": ctx.get("system"),
        "reply": ctx.get("reply"),
        "webhook": ctx.get("webhook"),
        "print": print,
        "json": json,
        "time": time,
    }


def _exec_code(code: str, ctx: dict) -> None:
    """执行自定义代码块：上下文键（如循环变量）会直接作为变量暴露。"""
    if not code.strip():
        return
    scope = _code_scope(ctx)
    for k, v in ctx.items():
        if isinstance(k, str) and k.isidentifier():
            scope.setdefault(k, v)
    exec(compile(code, f"<visual-plugin:{PLUGIN_MODULE}>", "exec"), scope)


def _loop_items(expr: Any, ctx: dict) -> list:
    """循环遍历列表：{{变量}} 或 Python 表达式（如 [1,2,3]）。"""
    expr = str(expr).strip()
    if expr.startswith("{{") and expr.endswith("}}"):
        return _resolve(ctx, expr[2:-2].strip()) or []
    try:
        items = eval(expr, {"__builtins__": _SAFE_BUILTINS}, dict(ctx))
    except Exception:  # noqa: BLE001
        items = []
    return items if isinstance(items, (list, tuple)) else []


def _seconds_until(hour: int, minute: int, weekday: Optional[int] = None, day: Optional[int] = None) -> float:
    """计算距离下一个目标触发时刻的秒数（含今天尚未到达的时刻）。"""
    now = datetime.datetime.now()
    for offset in range(0, 370):
        d = now + datetime.timedelta(days=offset)
        if weekday is not None and d.weekday() != weekday:
            continue
        if day is not None:
            last = calendar.monthrange(d.year, d.month)[1]
            if d.day != min(day, last):
                continue
        candidate = d.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return max(1.0, (candidate - now).total_seconds())
    return 60.0


@event_preprocessor
async def _visual_collect_preprocessor(bot: Bot, event: Event):
    """信息收集 / 选项交互：用户回复后继续之前挂起的流程，并阻止其它响应器处理该回复。"""
    key = _session_key(event)
    pend = _pending.pop(key, None)
    if pend is None:
        return
    ctx = pend["ctx"]
    ctx["event"] = event
    ctx["bot"] = bot
    reply_text = event.message.extract_plain_text()
    ctx["reply"] = reply_text
    ctx["reply_segments"] = [
        {"type": s.type, "data": dict(s.data)} for s in event.message
    ]
    if pend.get("kind") == "choice":
        # 选项交互：校验输入，非法则重新提示
        options = pend.get("options") or []
        var = pend.get("var") or "choice"
        text = reply_text.strip()
        _sess = ctx.get("session")
        if text == "0":
            ctx[var] = {"index": 0, "text": "退出"}
            if _sess is not None:
                _sess[var] = ctx[var]
            await _send(ctx, [{"type": "text", "value": "已退出"}], None)
            await pend["dispatcher"](ctx, 0)
        elif text.isdigit() and 1 <= int(text) <= len(options):
            idx = int(text)
            ctx[var] = {"index": idx, "text": _tpl(options[idx - 1], ctx)}
            if _sess is not None:
                _sess[var] = ctx[var]
            await pend["dispatcher"](ctx, idx)
        else:
            await _send(ctx, [{"type": "text", "value": "未知选项，请重新输入："}], None)
            _pending[key] = pend
        raise IgnoredException("handled by visual plugin choice")
    # 信息收集
    ctx[pend.get("key") or "reply"] = reply_text
    _sess = ctx.get("session")
    if _sess is not None:
        _sess[pend.get("key") or "reply"] = reply_text
    cont = pend.get("continuation")
    if cont is not None:
        await cont(ctx)
    raise IgnoredException("handled by visual plugin collect")
'''


def _sanitize_desc(desc: str) -> str:
    return " ".join((desc or "").splitlines())[:120]


def _safe_line(text: str) -> str:
    return re.sub(r'"""', "'''", (text or "").replace("\r", " ").replace("\n", " "))


def _next_in_flow(flow: dict, node_id: str, port: str = "next") -> Optional[str]:
    for e in flow.get("edges", []):
        if e.get("from") == node_id and e.get("port", "next") == port:
            return e.get("to")
    return None


def _py_literal(obj: Any) -> str:
    """把 Python 对象序列化为可直接嵌入生成代码的 Python 字面量。"""
    return repr(obj)


def _logic_cond_expr(cfg: dict) -> str:
    return f"_eval_logic({_py_literal(cfg)}, ctx)"


def _loop_items_expr(items: str) -> str:
    return f"_loop_items({_py_literal((items or '').strip())}, ctx)"


def _emit_step(node: dict, flow: dict) -> str:
    """把一个节点编译为异步步骤函数。"""
    nid = node["id"]
    ntype = node["type"]
    cfg = node.get("config") or {}
    lines = [
        '    ctx["__steps"] = ctx.get("__steps", 0) + 1',
        '    if ctx["__steps"] > 10000:\n        return',
    ]
    if ntype == "logic":
        expr = _logic_cond_expr(cfg)
        true_id = _next_in_flow(flow, nid, "true") or _next_in_flow(flow, nid, "next")
        false_id = _next_in_flow(flow, nid, "false")
        if true_id and false_id:
            lines.append(
                f"    if {expr}:\n        await _step_{true_id}(ctx)\n    else:\n        await _step_{false_id}(ctx)"
            )
        elif true_id:
            lines.append(f"    if {expr}:\n        await _step_{true_id}(ctx)")
        elif false_id:
            lines.append(f"    if not {expr}:\n        await _step_{false_id}(ctx)")
        else:
            lines.append(f"    if {expr}:\n        pass")
    elif ntype == "loop":
        var = (cfg.get("var") or "item").strip() or "item"
        items_expr = _loop_items_expr(cfg.get("items", ""))
        body_id = _next_in_flow(flow, nid, "next")
        end_id = cfg.get("end") or ""
        after_id = None
        if end_id:
            end_node = next((n for n in flow["nodes"] if n["id"] == end_id), None)
            if end_node:
                after_id = _next_in_flow(flow, end_id, "next")
        lines.append(f"    for {var} in {items_expr}:")
        if body_id:
            lines.append(f"        ctx[{var!r}] = {var}")
            lines.append(f"        await _step_{body_id}(ctx)")
        else:
            lines.append("        pass")
        lines.append(f"    ctx.pop({var!r}, None)")
        if after_id:
            lines.append(f"    await _step_{after_id}(ctx)")
    elif ntype == "api":
        method = (cfg.get("method") or "GET").upper()
        url = (cfg.get("url") or "").strip()
        headers = cfg.get("headers") or []
        headers_dict = {h.get("key", ""): h.get("value", "") for h in headers if h.get("key")}
        body = cfg.get("body", "")
        var = (cfg.get("var") or "api_resp").strip() or "api_resp"
        try:
            timeout = max(1, min(120, int(cfg.get("timeout", 10))))
        except (TypeError, ValueError):
            timeout = 10
        lines.append("    try:")
        lines.append(f"        _method = {_py_literal(method)}")
        lines.append(f"        _url = _tpl({_py_literal(url)}, ctx)")
        lines.append(f"        _headers = {_py_literal(headers_dict)}")
        lines.append("        _headers = {k: _tpl(str(v), ctx) for k, v in _headers.items()}")
        lines.append(f"        _body = _tpl({_py_literal(body)}, ctx)")
        lines.append(f"        async with httpx.AsyncClient(timeout={timeout}) as _client:")
        lines.append("            _body = (_body or '').strip()")
        lines.append("            if _body[:1] in ('{', '['):")
        lines.append("                try:")
        lines.append("                    _resp = await _client.request(_method, _url, headers=_headers, json=json.loads(_body))")
        lines.append("                except Exception:  # noqa: BLE001")
        lines.append("                    _resp = await _client.request(_method, _url, headers=_headers, content=_body)")
        lines.append("            elif _body:")
        lines.append("                _resp = await _client.request(_method, _url, headers=_headers, content=_body)")
        lines.append("            else:")
        lines.append("                _resp = await _client.request(_method, _url, headers=_headers)")
        lines.append("        _data = None")
        lines.append("        try:")
        lines.append("            _data = _resp.json()")
        lines.append("        except Exception:  # noqa: BLE001")
        lines.append("            pass")
        lines.append(
            f"        ctx[{_py_literal(var)}] = {{'status': _resp.status_code, 'text': _resp.text, "
            "'data': _data, 'headers': dict(_resp.headers)}"
        )
        lines.append("    except Exception as _exc:  # noqa: BLE001")
        lines.append(
            f"        ctx[{_py_literal(var)}] = {{'status': 0, 'error': str(_exc), "
            "'text': '', 'data': None, 'headers': {}}"
        )
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(f"    await _step_{next_id}(ctx)")
    elif ntype == "send_email":
        to = cfg.get("to", "")
        subject = cfg.get("subject", "")
        body = cfg.get("body", "")
        html = bool(cfg.get("html", False))
        lines.append(
            f"    await _send_email(ctx, {_py_literal(to)}, {_py_literal(subject)}, "
            f"{_py_literal(body)}, {_py_literal(html)})"
        )
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(f"    await _step_{next_id}(ctx)")
    elif ntype == "code":
        code = (cfg.get("code") or "").strip()
        if code:
            lines.append(f"    _exec_code({_py_literal(code)}, ctx)")
        else:
            lines.append("    pass")
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(f"    await _step_{next_id}(ctx)")
    elif ntype == "send":
        lines.append(
            f"    await _send(ctx, {_py_literal(cfg.get('messages') or [])}, "
            f"{_py_literal(cfg.get('target') or {})})"
        )
        if cfg.get("mode") == "finish":
            lines.append("    return")
        else:
            next_id = _next_in_flow(flow, nid, "next")
            if next_id:
                lines.append(f"    await _step_{next_id}(ctx)")
    elif ntype == "collect":
        key = cfg.get("key", "reply")
        prompt = cfg.get("prompt", "")
        if prompt:
            lines.append(
                f"    await _send(ctx, [{{\"type\": \"text\", \"value\": {_py_literal(prompt)}}}], None)"
            )
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(
                f"    _pending[_session_key(ctx.get('event'))] = "
                f"{{\"ctx\": ctx, \"key\": {_py_literal(key)}, "
                f"\"continuation\": _step_{next_id}}}"
            )
        lines.append("    return")
    elif ntype == "choice":
        # 选项交互：发送提示+选项，挂起等待选择
        prompt = cfg.get("prompt", "")
        options = cfg.get("options") or []
        var = (cfg.get("var") or "choice").strip() or "choice"
        lines.append(
            f"    _opt_lines = [f\"[{{i + 1}}] {{_tpl(opt, ctx)}}\" for i, opt in enumerate({_py_literal(options)})]"
        )
        lines.append(f"    _text = _tpl({_py_literal(prompt)}, ctx)")
        lines.append("    if _opt_lines:")
        lines.append("        _text = _text + '\\n' + '\\n'.join(_opt_lines)")
        lines.append("    _text = _text + '\\n[0] 退出\\n请输入您的选择：'")
        lines.append(
            "    await _send(ctx, [{\"type\": \"text\", \"value\": _text}], None)"
        )
        lines.append(
            f"    _pending[_session_key(ctx.get('event'))] = "
            f"{{\"kind\": \"choice\", \"ctx\": ctx, \"options\": {_py_literal(options)}, "
            f"\"var\": {_py_literal(var)}, \"prompt_text\": _text, "
            f"\"dispatcher\": _choice_{nid}}}"
        )
        lines.append("    return")
    elif ntype == "loop_end":
        lines.append("    pass")
    elif ntype == "conversation_entry":
        # 会话入口：创建/复用会话存储，并把会话中已收集的数据恢复到上下文
        lines.append('    _skey = _session_key(ctx.get("event"))')
        lines.append("    if _skey not in _sessions:")
        lines.append("        _sessions[_skey] = {}")
        lines.append("    _sess = _sessions[_skey]")
        lines.append("    for _k, _v in list(_sess.items()):")
        lines.append("        ctx[_k] = _v")
        lines.append('    ctx["session"] = _sess')
        lines.append('    ctx["session_key"] = _skey')
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(f"    await _step_{next_id}(ctx)")
    elif ntype == "session_end":
        # 会话结束：清除会话存储
        lines.append('    _skey = ctx.get("session_key") or _session_key(ctx.get("event"))')
        lines.append("    _sessions.pop(_skey, None)")
        lines.append('    ctx.pop("session", None)')
        lines.append('    ctx.pop("session_key", None)')
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(f"    await _step_{next_id}(ctx)")
    else:
        next_id = _next_in_flow(flow, nid, "next")
        if next_id:
            lines.append(f"    await _step_{next_id}(ctx)")
        else:
            lines.append("    pass")
    return f"async def _step_{nid}(ctx):\n" + "\n".join(lines)


def _emit_choice_dispatcher(node: dict, flow: dict) -> str:
    """选项交互的分发器：按用户选择的分支继续执行；0 为退出会话。"""
    nid = node["id"]
    cfg = node.get("config") or {}
    options = cfg.get("options") or []
    lines = [f"async def _choice_{nid}(ctx, index):"]
    lines.append("    if index == 0:")
    lines.append('        _skey = ctx.get("session_key") or _session_key(ctx.get("event"))')
    lines.append("        _sessions.pop(_skey, None)")
    lines.append('        ctx.pop("session", None)')
    lines.append('        ctx.pop("session_key", None)')
    target = _next_in_flow(flow, nid, "opt_0")
    if target:
        lines.append(f"        await _step_{target}(ctx)")
    else:
        lines.append("        pass")
    for i in range(1, len(options) + 1):
        target = _next_in_flow(flow, nid, f"opt_{i}")
        lines.append(f"    elif index == {i}:")
        if target:
            lines.append(f"        await _step_{target}(ctx)")
        else:
            lines.append("        pass")
    return "\n".join(lines)


def _parse_time(value: str) -> tuple[int, int]:
    parts = (value or "09:00").split(":")
    try:
        hour = min(23, max(0, int(parts[0])))
        minute = min(59, max(0, int(parts[1])))
    except (IndexError, ValueError):
        hour, minute = 9, 0
    return hour, minute


def _schedule_delay_expr(cfg: dict) -> str:
    mode = cfg.get("mode", "interval")
    if mode == "interval":
        try:
            interval = max(1, int(cfg.get("interval", 60)))
        except (TypeError, ValueError):
            interval = 60
        return str(interval)
    hour, minute = _parse_time(cfg.get("time", "09:00"))
    if mode == "daily":
        return f"_seconds_until({hour}, {minute})"
    if mode == "weekly":
        try:
            weekday = int(cfg.get("weekday", 1))
        except (TypeError, ValueError):
            weekday = 1
        return f"_seconds_until({hour}, {minute}, weekday={min(6, max(0, weekday))})"
    if mode == "monthly":
        try:
            day = int(cfg.get("day", 1))
        except (TypeError, ValueError):
            day = 1
        return f"_seconds_until({hour}, {minute}, day={min(31, max(1, day))})"
    return "60"


def _emit_entries(flow: dict, module: str) -> list[str]:
    sections: list[str] = []
    for node in flow.get("nodes", []):
        ntype = node["type"]
        cfg = node.get("config") or {}
        nid = node["id"]
        next_id = _next_in_flow(flow, nid, "next")
        call = f"await _step_{next_id}(ctx)" if next_id else "pass"
        if ntype == "listener_group":
            groups = cfg.get("groups", "all").strip() or "all"
            ids_lit = _py_literal(
                groups if groups == "all" else [int(x) for x in groups.split(",") if x.strip()]
            )
            keywords = [k.strip() for k in cfg.get("keywords", "").split(",") if k.strip()]
            kw_lit = _py_literal(keywords)
            at_me_lit = _py_literal(bool(cfg.get("at_me", False)))
            match = cfg.get("match", "contains")
            match_expr = {
                "starts_with": "any(text.startswith(k) for k in keywords)",
                "regex": "any(re.search(k, text) for k in keywords)",
                "contains": "any(k in text for k in keywords)",
            }.get(match, "any(k in text for k in keywords)")
            sections.append(
                f"""# ---------- 监听：群聊 ----------
def _rule_{nid}(event: Event) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    ids = {ids_lit}
    if ids != "all" and event.group_id not in ids:
        return False
    at_me = {at_me_lit}
    if at_me and not event.to_me:
        return False
    keywords = {kw_lit}
    if keywords:
        text = event.message.extract_plain_text().strip()
        if not {match_expr}:
            return False
    return True


matcher_{nid} = on_message(rule=_rule_{nid}, priority=10, block=True)


@matcher_{nid}.handle()
async def _handle_{nid}(bot: Bot, event: GroupMessageEvent):
    ctx = _build_ctx(bot, event)
    {call}
"""
            )
        elif ntype == "listener_private":
            users = cfg.get("users", "all").strip() or "all"
            ids_lit = _py_literal(
                users if users == "all" else [int(x) for x in users.split(",") if x.strip()]
            )
            keywords = [k.strip() for k in cfg.get("keywords", "").split(",") if k.strip()]
            kw_lit = _py_literal(keywords)
            match = cfg.get("match", "contains")
            match_expr = {
                "starts_with": "any(text.startswith(k) for k in keywords)",
                "regex": "any(re.search(k, text) for k in keywords)",
                "contains": "any(k in text for k in keywords)",
            }.get(match, "any(k in text for k in keywords)")
            sections.append(
                f"""# ---------- 监听：私信 ----------
def _rule_{nid}(event: Event) -> bool:
    if not isinstance(event, PrivateMessageEvent):
        return False
    ids = {ids_lit}
    if ids != "all" and event.user_id not in ids:
        return False
    keywords = {kw_lit}
    if keywords:
        text = event.message.extract_plain_text().strip()
        if not {match_expr}:
            return False
    return True


matcher_{nid} = on_message(rule=_rule_{nid}, priority=10, block=True)


@matcher_{nid}.handle()
async def _handle_{nid}(bot: Bot, event: PrivateMessageEvent):
    ctx = _build_ctx(bot, event)
    {call}
"""
            )
        elif ntype == "listener_webhook":
            path = cfg.get("path", "").strip()
            if not path:
                path = f"/webhook/{module}"
            if not path.startswith("/"):
                path = "/" + path
            var = (cfg.get("var") or "webhook").strip() or "webhook"
            call_fire = f"_spawn(_step_{next_id}(ctx))" if next_id else "pass"
            sections.append(
                f"""# ---------- 监听：WebHook ----------
driver = get_driver()


@driver.server_app.post({path!r})
async def _webhook_{nid}(request):
    payload = {{}}
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        try:
            form = await request.form()
            if form:
                payload = {{k: str(v) for k, v in form.items()}}
            else:
                text = (await request.body()).decode("utf-8", errors="replace").strip()
                if text:
                    payload = {{"text": text}}
        except Exception:  # noqa: BLE001
            pass
    ctx = _build_ctx(None, None, webhook=payload)
    _attach_bot(ctx)
    ctx[{_py_literal(var)}] = payload
    {call_fire}
    return {{"ok": True}}
"""
            )
        elif ntype == "schedule":
            delay = _schedule_delay_expr(cfg)
            sections.append(
                f"""# ---------- 定时任务 ----------
driver = get_driver()


@driver.on_startup
async def _schedule_{nid}():
    async def _task():
        while True:
            try:
                await asyncio.sleep({delay})
                nonebot.logger.info(f"[可视化插件] 定时任务触发：{{PLUGIN_NAME}}")
                ctx = _build_ctx(None, None)
                _attach_bot(ctx)
                {call}
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                nonebot.logger.warning(f"[可视化插件] 定时任务异常：{{exc}}")

    _spawn(_task())
"""
            )
    return sections


def generate_code(plugin: VisualPlugin, bot_name: str = "") -> str:
    """把可视化流程编译为直接控制流的 OneBot V11 NoneBot 插件源码。"""
    flow = _migrate_flow(plugin.flow)
    _validate_flow(flow, require_entry=True)
    code = (
        _RUNTIME_TEMPLATE.replace(
            "%%PLUGIN_NAME%%", json.dumps(plugin.name, ensure_ascii=True)
        )
        .replace(
            "%%PLUGIN_MODULE%%", json.dumps(plugin.module, ensure_ascii=True)
        )
        .replace("%%BOT_NAME%%", json.dumps(bot_name, ensure_ascii=True))
        .replace(
            "%%EMAIL_CONFIG_PATH%%",
            json.dumps(str(config.EMAIL_FILE), ensure_ascii=True),
        )
    )
    step_parts = [
        _emit_step(node, flow)
        for node in flow.get("nodes", [])
        if node["type"] not in ("listener_group", "listener_private", "listener_webhook", "schedule")
    ]
    choice_parts = [
        _emit_choice_dispatcher(node, flow)
        for node in flow.get("nodes", [])
        if node["type"] == "choice"
    ]
    sections = _emit_entries(flow, plugin.module)
    header = (
        f'"""\n{_safe_line(plugin.name)}'
        + (f"：{_safe_line(_sanitize_desc(plugin.description))}" if plugin.description else "")
        + '\n由 NoneBot2 WebUI 可视化插件生成（OneBot V11）\n"""\n\n'
    )
    body = "\n\n".join(step_parts + choice_parts) if (step_parts or choice_parts) else "# （暂无流程节点）"
    return header + code + "\n\n" + body + "\n\n" + "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# 装配 / 卸载
# ---------------------------------------------------------------------------

def install_to_bot(plugin_id: str, bot_id: str) -> dict:
    """把生成插件写入机器人插件目录（不自动重启，由路由层处理）。"""
    plugin = get_visual_plugin(plugin_id)
    if plugin is None:
        raise KeyError(plugin_id)
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    code = generate_code(plugin, bot_name=bot.name)
    result = install_plugin_file(bot_id, f"{plugin.module}.py", code.encode("utf-8"))
    plugins = [VisualPlugin(**p) for p in list_visual_plugins()]
    target = next((p for p in plugins if p.id == plugin_id), None)
    if target is not None:
        entries = [e for e in target.installed if e.get("bot_id") != bot_id]
        entries.append({"bot_id": bot_id, "installed_at": _now()})
        target.installed = entries
        target.updated_at = _now()
        _save_all(plugins)
    return {**result, "module": plugin.module}


def uninstall_from_bot(plugin_id: str, bot_id: str) -> dict:
    plugin = get_visual_plugin(plugin_id)
    if plugin is None:
        raise KeyError(plugin_id)
    bot = bot_manager.get_bot(bot_id)
    if bot is None:
        raise ValueError("机器人不存在")
    plugin_dir = bot_manager.plugin_dir_path(bot)
    target = plugin_dir / f"{plugin.module}.py"
    removed = False
    if target.exists():
        target.unlink()
        removed = True
    disabled_file = Path(bot.directory) / "webui_disabled_plugins.json"
    if disabled_file.exists():
        try:
            disabled = set(json.loads(disabled_file.read_text(encoding="utf-8")))
            disabled.discard(plugin.module)
            disabled_file.write_text(
                json.dumps(sorted(disabled), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, OSError):
            pass
    plugins = [VisualPlugin(**p) for p in list_visual_plugins()]
    target_p = next((p for p in plugins if p.id == plugin_id), None)
    if target_p is not None:
        target_p.installed = [e for e in target_p.installed if e.get("bot_id") != bot_id]
        target_p.updated_at = _now()
        _save_all(plugins)
    return {"removed": removed, "module": plugin.module}
