"""可视化插件：流程存储、校验与 NoneBot(OneBot V11) 插件代码生成。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from . import config
from .bot_manager import bot_manager
from .plugin_manager import install_plugin_file, remove_plugin_files
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
        "default": {
            "mode": "interval",  # interval | daily | weekly | monthly
            "interval": 60,
            "times": ["09:00"],  # 定点模式可配置多个时间点
            "weekdays": [0, 1, 2, 3, 4],  # weekly：0=周一 … 6=周日，可多选
            "day": 1,  # monthly：每月几号
            "run_on_start": False,  # 启动后立即执行一次
        },
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
    "storage": {
        "category": "feature",
        "label": "数据存储",
        "default": {
            "action": "set",  # set | get | delete | append | incr | keys | clear
            "key": "",  # 键名，支持 {{模板}}
            "value": "",  # set / append 的写入值，支持 {{模板}}
            "json": False,  # 写入值按 JSON 解析（存数组 / 对象时必须开）
            "var": "store",  # get / keys 的结果变量
            "fallback": "",  # get 未命中时的默认值
        },
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
    "qzone": {
        "category": "action",
        "label": "获取空间动态",
        "default": {
            "source": "user",  # user（指定 QQ 的说说）| feeds（好友动态）| detail（单条详情）
            "target_uin": "",  # 留空=触发者 / 机器人自己
            "pos": 0,  # 起始位置，0 为最新
            "num": 1,  # 获取条数，1=只取最新一条
            "page_num": 1,  # feeds 模式页码
            "tid": "",  # detail 模式：动态 ID
            "uin": "",  # detail 模式：作者 QQ
            "var": "qzone",
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

# 「数据存储」组件支持的操作，顺序即前端下拉顺序
STORAGE_ACTIONS = ("set", "get", "append", "incr", "delete", "keys", "clear")

# 固定键名的字符集约束（含模板的键名留到运行时再判断）
STORAGE_KEY_RE = re.compile(r"^[\w\-\u4e00-\u9fff]{1,64}$")

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

# 保留变量名：state 是跨触发保留的全局变量，store 是长期存储接口，不能被节点当作普通变量名占用
RESERVED_VARS = frozenset({"state", "store"})

# 定时任务的触发时间格式（HH:MM，允许 9:00 这种单位数小时）
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _require_ident(cfg: dict, key: str, node_id: str, default: str) -> str:
    """校验配置字段必须是合法 Python 标识符，返回规范化后的值。"""
    value = str(cfg.get(key) or "").strip() or default
    if not IDENT_RE.match(value):
        raise ValueError(f"节点 {node_id} 的「变量名」必须是合法 Python 变量名")
    if value in RESERVED_VARS:
        raise ValueError(f"节点 {node_id} 的「变量名」不能使用保留名「{value}」（全局变量）")
    return value


def _validate_node_config(ntype: str, cfg: dict, node_id: str) -> None:
    """按节点类型校验配置内容，防止生成代码注入与非法配置。"""
    if ntype == "loop":
        _require_ident(cfg, "var", node_id, "item")
    elif ntype == "collect":
        _require_ident(cfg, "key", node_id, "reply")
    elif ntype in ("api", "choice", "qzone"):
        default_var = {"api": "api_resp", "choice": "choice", "qzone": "qzone"}[ntype]
        _require_ident(cfg, "var", node_id, default_var)
        if ntype == "qzone":
            source = str(cfg.get("source") or "user").strip().lower()
            if source not in ("user", "feeds", "detail"):
                raise ValueError(f"节点 {node_id} 的「获取方式」不合法")
            for key, low, high in (("num", 1, 100), ("pos", 0, 10000), ("page_num", 1, 1000)):
                raw = cfg.get(key)
                if raw is None or raw == "":
                    continue
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    raise ValueError(f"节点 {node_id} 的「{key}」必须是整数") from None
                if not low <= value <= high:
                    raise ValueError(f"节点 {node_id} 的「{key}」超出范围（{low}~{high}）")
    elif ntype == "storage":
        action = str(cfg.get("action") or "set").strip().lower()
        if action not in STORAGE_ACTIONS:
            raise ValueError(f"节点 {node_id} 的「操作」不合法")
        if action in ("get", "keys"):
            _require_ident(cfg, "var", node_id, "store")
        key = str(cfg.get("key") or "").strip()
        if action not in ("clear", "keys") and not key:
            raise ValueError(f"节点 {node_id} 的「数据键名」不能为空")
        if len(key) > 200:
            raise ValueError(f"节点 {node_id} 的「数据键名」过长（不超过 200 字符）")
        if key and "{{" not in key and not STORAGE_KEY_RE.match(key):
            raise ValueError(
                f"节点 {node_id} 的「数据键名」只能包含中英文、数字、下划线、短横线，"
                "最多 64 个字符（也不允许出现点号）"
            )
    elif ntype == "schedule":
        mode = str(cfg.get("mode") or "interval").strip().lower()
        if mode not in ("interval", "daily", "weekly", "monthly"):
            raise ValueError(f"节点 {node_id} 的「触发模式」不合法")
        if mode == "interval":
            try:
                value = int(cfg.get("interval", 60))
            except (TypeError, ValueError):
                raise ValueError(f"节点 {node_id} 的「间隔」必须是整数秒") from None
            if not 1 <= value <= 86400:
                raise ValueError(f"节点 {node_id} 的「间隔」超出范围（1~86400 秒）")
        else:
            times = cfg.get("times")
            if not isinstance(times, list) or not times:
                times = [cfg.get("time") or "09:00"]  # 兼容旧流程的单值 time
            if len(times) > 24:
                raise ValueError(f"节点 {node_id} 最多配置 24 个触发时间")
            for item in times:
                text = str(item).strip()
                if not TIME_RE.match(text):
                    raise ValueError(f"节点 {node_id} 的触发时间「{text}」格式应为 HH:MM")
            if mode == "weekly":
                weekdays = cfg.get("weekdays")
                if weekdays is None:  # 兼容旧流程的单值 weekday
                    weekdays = [cfg.get("weekday", 1)]
                if not isinstance(weekdays, list):
                    raise ValueError(f"节点 {node_id} 的「星期」必须是列表")
                for item in weekdays:
                    try:
                        value = int(item)
                    except (TypeError, ValueError):
                        raise ValueError(f"节点 {node_id} 的「星期」必须是 0~6 的整数") from None
                    if not 0 <= value <= 6:
                        raise ValueError(f"节点 {node_id} 的「星期」必须是 0~6 的整数")
            if mode == "monthly":
                try:
                    value = int(cfg.get("day", 1))
                except (TypeError, ValueError):
                    raise ValueError(f"节点 {node_id} 的「每月几号」必须是整数") from None
                if not 1 <= value <= 31:
                    raise ValueError(f"节点 {node_id} 的「每月几号」超出范围（1~31）")
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
    """兼容旧版本流程：条件节点改名，定时任务补齐多时间点 / 多星期字段。"""
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
        elif ntype == "schedule":
            node = {**node, "config": _normalize_schedule_config(node.get("config") or {})}
        nodes.append(node)
    return {"nodes": nodes, "edges": flow.get("edges") or []}


def _normalize_schedule_config(cfg: dict) -> dict:
    """把旧的单值 time / weekday 升级为 times / weekdays 列表（保留可编辑性）。"""
    out = dict(cfg)
    times = out.get("times")
    if not isinstance(times, list) or not times:
        out["times"] = [str(out.get("time") or "09:00").strip() or "09:00"]
    else:
        out["times"] = [str(x).strip() for x in times if str(x).strip()] or ["09:00"]
    weekdays = out.get("weekdays")
    if not isinstance(weekdays, list) or not weekdays:
        try:
            legacy = int(out.get("weekday", 1))
        except (TypeError, ValueError):
            legacy = 1
        out["weekdays"] = [min(6, max(0, legacy))]
    else:
        cleaned: List[int] = []
        for item in weekdays:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 6:
                cleaned.append(value)
        out["weekdays"] = sorted(set(cleaned)) or [0]
    out.pop("time", None)
    out.pop("weekday", None)
    return out


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
import threading
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


# ---------- 全局变量：跨触发保留，随插件落盘 ----------
def _state_path() -> str:
    base = os.path.dirname(os.path.abspath(globals().get("__file__") or "."))
    return os.path.join(base, f"vplugin_state_{PLUGIN_MODULE}.json")


def _state_load() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _state_fingerprint() -> str:
    try:
        return json.dumps(_STATE, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return ""


_STATE: Dict[str, Any] = _state_load()
_STATE_SAVED_FP = _state_fingerprint()


def _state_save() -> None:
    """有变化才写盘；先写临时文件再替换，避免留下半截 JSON。"""
    global _STATE_SAVED_FP
    fingerprint = _state_fingerprint()
    if fingerprint == _STATE_SAVED_FP:
        return
    path = _state_path()
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as fp:
            json.dump(_STATE, fp, ensure_ascii=False, indent=2, default=str)
        os.replace(path + ".tmp", path)
    except (OSError, TypeError, ValueError) as exc:  # noqa: BLE001
        nonebot.logger.warning(f"[可视化插件] 全局变量保存失败：{exc}")
        return
    _STATE_SAVED_FP = fingerprint


# ---------- 长期存储：跨触发、跨重启保留，面板可读写 ----------
try:
    import fcntl  # Linux / macOS
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:
    import msvcrt  # Windows
except ImportError:  # pragma: no cover - 非 Windows
    msvcrt = None

STORE_LIMIT_BYTES = 2 * 1024 * 1024
STORE_LIMIT_KEYS = 2000
STORE_APPEND_LIMIT = 5000
# 键名不能含点：模板里的点路径（{{store.a.b}}）靠点分段
STORE_KEY_RE = re.compile(r"^[\\w\\-\\u4e00-\\u9fff]{1,64}$")


def _store_path() -> str:
    base = os.path.dirname(os.path.abspath(globals().get("__file__") or "."))
    return os.path.join(base, f"vplugin_store_{PLUGIN_MODULE}.json")


class _StoreFileLock:
    """跨进程文件锁：面板改数据与机器人写数据撞车时互斥。

    拿不到锁也继续执行，靠写入后的 mtime 比对兜底，不让存储操作把流程卡死。
    """

    def __init__(self, path: str):
        self._path = path
        self._fh = None

    def __enter__(self):
        try:
            self._fh = open(self._path, "a+b")
        except OSError:
            self._fh = None
            return self
        try:
            if fcntl is not None:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
        except OSError:
            pass
        return self

    def __exit__(self, *exc_info):
        try:
            if self._fh is not None:
                if fcntl is not None:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
        return False


_STORE: Dict[str, dict] = {}
_STORE_MTIME: float = -1.0
_STORE_LOCK = threading.RLock()


def _store_stat_mtime() -> float:
    try:
        return os.path.getmtime(_store_path())
    except OSError:
        return -1.0


def _store_load_locked() -> None:
    """从磁盘读入内存；面板刚改过文件时靠它跟上，避免整份覆盖别人的改动。"""
    global _STORE, _STORE_MTIME
    data: Dict[str, dict] = {}
    try:
        with open(_store_path(), encoding="utf-8") as fp:
            raw = json.load(fp)
        if isinstance(raw, dict) and isinstance(raw.get("items"), dict):
            data = {k: v for k, v in raw["items"].items() if isinstance(v, dict)}
    except (OSError, ValueError):
        data = {}
    _STORE = data
    _STORE_MTIME = _store_stat_mtime()


def _store_reload_if_stale() -> None:
    if _store_stat_mtime() != _STORE_MTIME:
        _store_load_locked()


def _store_flush_locked() -> None:
    global _STORE_MTIME
    path = _store_path()
    payload = {"version": 1, "items": _STORE}
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2, default=str)
        os.replace(path + ".tmp", path)
    except (OSError, TypeError, ValueError) as exc:  # noqa: BLE001
        nonebot.logger.warning(f"[可视化插件] 存储写入失败：{exc}")
        return
    _STORE_MTIME = _store_stat_mtime()


def _store_key(key: Any) -> str:
    text = str(key if key is not None else "").strip()
    if not text:
        raise ValueError("存储键名不能为空")
    if not STORE_KEY_RE.match(text):
        raise ValueError(f"存储键名「{text}」不合法：只能包含中英文、数字、下划线、短横线，最多 64 个字符")
    return text


def _store_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _store_check_limits() -> None:
    if len(_STORE) > STORE_LIMIT_KEYS:
        raise ValueError(f"存储键数量已达上限 {STORE_LIMIT_KEYS} 个，请清理不再需要的数据")
    try:
        text = json.dumps(_STORE, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return
    if len(text.encode("utf-8")) > STORE_LIMIT_BYTES:
        raise ValueError(
            f"存储占用超过上限 {STORE_LIMIT_BYTES // 1024} KB，请清理不再需要的数据"
        )


def _store_commit(key: str, item: dict) -> None:
    """在已持有内存锁与文件锁的前提下落盘；超限则回滚，不留下半截脏数据。"""
    previous = _STORE.get(key)
    _STORE[key] = item
    try:
        _store_check_limits()
    except ValueError:
        if previous is None:
            _STORE.pop(key, None)
        else:
            _STORE[key] = previous
        raise
    _store_flush_locked()


def _store_get(key: Any, default: Any = None) -> Any:
    text = _store_key(key)
    with _STORE_LOCK:
        _store_reload_if_stale()
        item = _STORE.get(text)
    if not isinstance(item, dict):
        return default
    return item.get("v", default)


def _store_set(key: Any, value: Any) -> Any:
    text = _store_key(key)
    with _STORE_LOCK:
        with _StoreFileLock(_store_path() + ".lock"):
            _store_load_locked()
            _store_commit(text, {"v": value, "t": _store_now()})
    return value


def _store_delete(key: Any) -> bool:
    text = _store_key(key)
    with _STORE_LOCK:
        with _StoreFileLock(_store_path() + ".lock"):
            _store_load_locked()
            removed = _STORE.pop(text, None) is not None
            if removed:
                _store_flush_locked()
    return removed


def _store_append(key: Any, item: Any, limit: int = STORE_APPEND_LIMIT) -> list:
    text = _store_key(key)
    with _STORE_LOCK:
        with _StoreFileLock(_store_path() + ".lock"):
            _store_load_locked()
            current = _STORE.get(text) or {}
            items = current.get("v")
            items = list(items) if isinstance(items, list) else []
            items.append(item)
            if limit and len(items) > limit:
                items = items[-limit:]
            _store_commit(text, {"v": items, "t": _store_now()})
    return items


def _store_incr(key: Any, delta: Any = 1) -> int:
    text = _store_key(key)
    try:
        step = int(delta)
    except (TypeError, ValueError):
        step = 1
    with _STORE_LOCK:
        with _StoreFileLock(_store_path() + ".lock"):
            _store_load_locked()
            current = _STORE.get(text) or {}
            try:
                value = int(current.get("v") or 0) + step
            except (TypeError, ValueError):
                value = step
            _store_commit(text, {"v": value, "t": _store_now()})
    return value


def _store_keys(prefix: Any = "") -> list:
    text = str(prefix if prefix is not None else "")
    with _STORE_LOCK:
        _store_reload_if_stale()
        return sorted(k for k in _STORE if k.startswith(text))


def _store_clear(key: Any = "") -> bool:
    text = str(key if key is not None else "").strip()
    with _STORE_LOCK:
        with _StoreFileLock(_store_path() + ".lock"):
            _store_load_locked()
            if text:
                removed = _STORE.pop(_store_key(text), None) is not None
            else:
                removed = bool(_STORE)
                _STORE.clear()
            if removed:
                _store_flush_locked()
    return removed


def _store_value(value: Any, json_mode: bool) -> Any:
    """节点里填的写入值：开了 JSON 开关就按字面量解析（存数组/对象要用它）。"""
    if not json_mode or not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return value


def _store_node(action: str, key: Any, value: Any, json_mode: bool = False, fallback: Any = None) -> Any:
    """节点调用的统一入口：出错只记日志，不中断整条流程。"""
    try:
        if action == "set":
            return _store_set(key, _store_value(value, json_mode))
        if action == "get":
            return _store_get(key, fallback)
        if action == "delete":
            return _store_delete(key)
        if action == "append":
            return _store_append(key, _store_value(value, json_mode))
        if action == "incr":
            return _store_incr(key, value)
        if action == "keys":
            return _store_keys(key)
        if action == "clear":
            return _store_clear(key)
    except Exception as exc:  # noqa: BLE001
        nonebot.logger.warning(f"[可视化插件] 存储操作失败（{action}）：{exc}")
    return fallback


def _store_expr(expr: Any, ctx: dict, json_mode: bool = False) -> Any:
    """节点写入值：整串就是一个 {{变量}} 时取原值（保留 list/dict），否则按模板渲染。"""
    text = str(expr if expr is not None else "")
    stripped = text.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        raw = _resolve(ctx, stripped[2:-2].strip())
        if json_mode:
            return raw
        return "" if raw is None else str(raw)
    return _store_value(_tpl(text, ctx), json_mode)


class _StoreProxy:
    """自定义代码里的存储接口：store.set("k", 1) / store.get("k") / store.incr("k")。"""

    limit_bytes = STORE_LIMIT_BYTES
    limit_keys = STORE_LIMIT_KEYS

    def get(self, key: Any, default: Any = None) -> Any:
        return _store_get(key, default)

    def set(self, key: Any, value: Any) -> Any:
        return _store_set(key, value)

    def delete(self, key: Any) -> bool:
        return _store_delete(key)

    def append(self, key: Any, item: Any, limit: int = STORE_APPEND_LIMIT) -> list:
        return _store_append(key, item, limit)

    def incr(self, key: Any, delta: Any = 1) -> int:
        return _store_incr(key, delta)

    def keys(self, prefix: Any = "") -> list:
        return _store_keys(prefix)

    def clear(self) -> bool:
        return _store_clear()

    def items(self) -> Dict[str, Any]:
        with _STORE_LOCK:
            _store_reload_if_stale()
            return {k: v.get("v") for k, v in _STORE.items()}

    def __contains__(self, key: Any) -> bool:
        try:
            return _store_key(key) in self.items()
        except ValueError:
            return False

    def __repr__(self) -> str:
        return f"<store {_store_path()}>"


store = _StoreProxy()
_store_load_locked()


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
        if isinstance(obj, _StoreProxy):
            obj = obj.items()
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


_VAR_RE = re.compile(r"\\{\\{\\s*([A-Za-z_\\u4e00-\\u9fff][\\w.\\[\\]0-9]*)\\s*\\}\\}")


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
    ctx["state"] = _STATE
    ctx["store"] = store
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


_QZONE_IMG_KEYS = ("url", "pic", "src", "picUrl", "pic_url", "origin_url", "image")


def _qzone_item(raw: Any) -> dict:
    """把不同协议端的说说 / 动态结构规整为统一字段。"""
    if not isinstance(raw, dict):
        return {}
    content = raw.get("content")
    if content is None:
        content = raw.get("html") or raw.get("text") or raw.get("summary") or ""
    content = re.sub(r"<[^>]+>", "", str(content or "")).replace("&nbsp;", " ").strip()
    images = []
    raw_images = raw.get("images") or raw.get("pics") or []
    if isinstance(raw_images, (list, tuple)):
        for item in raw_images:
            if isinstance(item, str):
                if item:
                    images.append(item)
            elif isinstance(item, dict):
                for key in _QZONE_IMG_KEYS:
                    if item.get(key):
                        images.append(str(item[key]))
                        break
    try:
        ts = int(raw.get("time") or raw.get("created_time") or 0)
    except (TypeError, ValueError):
        ts = 0
    return {
        "tid": str(raw.get("tid") or raw.get("key") or raw.get("id") or ""),
        "uin": (
            raw.get("uin")
            or raw.get("user_id")
            or raw.get("target_uin")
            or raw.get("qq")
        ),
        "nickname": (
            raw.get("nickname")
            or raw.get("nick_name")
            or raw.get("nick")
            or raw.get("name")
            or ""
        ),
        "content": content,
        "time": ts,
        "time_text": (
            datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
        ),
        "images": images,
        "comment_count": raw.get("comment_count", raw.get("comment_num", 0)) or 0,
        "like_count": raw.get("like_count", raw.get("like_num", 0)) or 0,
        "is_private": bool(raw.get("is_private", False)),
        "raw": raw,
    }


def _qzone_uin(value: Any) -> Any:
    """把 QQ 号规整为 int（不是纯数字时原样返回字符串）。"""
    text = str(value or "").strip()
    return int(text) if text.isdigit() else text


async def _qzone_nickname(bot: Any, uin: Any, cache: dict) -> str:
    """查询 QQ 昵称，用于补齐说说列表里缺失的发布者信息。

    同一个 QQ 在一次获取里只查一次；任何失败都返回空串，不影响动态本身。
    """
    key = str(uin or "").strip()
    if not key:
        return ""
    if key in cache:
        return cache[key]
    name = ""
    if key.isdigit():
        try:
            info = await bot.call_api("get_stranger_info", user_id=int(key))
            if isinstance(info, dict):
                name = str(info.get("nickname") or info.get("nick") or "")
        except Exception:  # noqa: BLE001
            name = ""
    cache[key] = name
    return name


def _qzone_text(items: list) -> str:
    """把动态列表拼成便于直接发送的纯文本。"""
    lines = []
    for item in items:
        content = str(item.get("content") or "").strip()
        if len(content) > 200:
            content = content[:200] + "…"
        head = item.get("time_text") or ""
        if item.get("nickname"):
            head = f"{item['nickname']} {head}".strip()
        line = f"【{head}】{content}" if head else content
        if item.get("images"):
            line += f"（{len(item['images'])} 张图）"
        lines.append(line)
    return "\\n".join(x for x in lines if x)


async def _qzone_fetch(ctx: dict, cfg: dict) -> dict:
    """获取 QQ 空间动态：指定 QQ 的说说 / 好友动态 / 单条详情。

    依赖协议端（NapCat / SnowLuma 等）提供的 QQ 空间扩展接口。任何失败都
    不抛异常，而是把原因写进返回值的 error 字段，避免中断整个流程。
    """
    source = str(cfg.get("source") or "user").strip().lower()
    if source not in ("user", "feeds", "detail"):
        source = "user"
    result: dict = {
        "ok": False,
        "source": source,
        "items": [],
        "count": 0,
        "total": 0,
        "text": "",
        "error": "",
        "raw": None,
    }
    bot = _resolve_bot(ctx)
    if bot is None:
        result["error"] = "当前没有已连接的机器人"
        nonebot.logger.warning("[可视化插件] 获取空间动态失败：{}", result["error"])
        return result
    data: Any = None
    items: list = []
    author_hint = ""  # 说说列表 / 单条详情接口不返回作者，用请求的 QQ 补齐
    try:
        if source == "detail":
            tid = str(_tpl(cfg.get("tid") or "", ctx)).strip()
            if not tid:
                result["error"] = "未指定动态 ID（tid）"
                return result
            uin = str(_tpl(cfg.get("uin") or cfg.get("target_uin") or "", ctx)).strip()
            if not uin:
                uin = str(ctx.get("user_id") or ctx.get("bot_id") or "")
            author_hint = uin
            params = {"tid": tid}
            if uin:
                params["uin"] = uin
            try:
                data = await bot.call_api("get_qzone_msg_detail", **params)
            except Exception:  # noqa: BLE001
                data = None
            if isinstance(data, dict):
                msglist = data.get("msglist")
                if isinstance(msglist, (list, tuple)):
                    items = list(msglist)
                elif data.get("tid") or data.get("content"):
                    items = [data]
            if not items and uin:
                # 回退：从该用户的说说列表里按 tid 精确查找
                try:
                    data = await bot.call_api(
                        "get_qzone_msg_list", target_uin=uin, pos=0, num=50
                    )
                    for item in (data or {}).get("msglist") or []:
                        if str(item.get("tid") or item.get("key") or "") == tid:
                            items = [item]
                            break
                except Exception:  # noqa: BLE001
                    pass
            if not items:
                result["error"] = "未找到该动态（协议端可能不支持空间接口，或 tid 有误）"
        else:
            try:
                num = max(1, min(100, int(cfg.get("num", 1))))
            except (TypeError, ValueError):
                num = 1
            if source == "feeds":
                try:
                    page_num = max(1, int(cfg.get("page_num", 1)))
                except (TypeError, ValueError):
                    page_num = 1
                data = await bot.call_api(
                    "get_qzone_feeds", page_num=page_num, count=num
                )
                items = list((data or {}).get("feeds") or [])
            else:
                uin = str(_tpl(cfg.get("target_uin") or "", ctx)).strip()
                if not uin:
                    uin = str(ctx.get("user_id") or ctx.get("bot_id") or "")
                if not uin:
                    result["error"] = "未指定目标 QQ 号，且当前上下文里没有发送者"
                    return result
                author_hint = uin
                try:
                    pos = max(0, int(cfg.get("pos", 0)))
                except (TypeError, ValueError):
                    pos = 0
                data = await bot.call_api(
                    "get_qzone_msg_list", target_uin=uin, pos=pos, num=num
                )
                items = list((data or {}).get("msglist") or [])
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc) or exc.__class__.__name__
        nonebot.logger.warning("[可视化插件] 获取空间动态失败：{}", result["error"])
        return result
    normalized = [x for x in (_qzone_item(i) for i in items) if x]
    if author_hint:
        for one in normalized:
            if not one.get("uin"):
                one["uin"] = _qzone_uin(author_hint)
    # 发布者昵称：协议端没返回时补查一次（同一 QQ 只查一次，失败留空）
    nick_cache: dict = {}
    for one in normalized:
        if not one.get("nickname") and one.get("uin"):
            one["nickname"] = await _qzone_nickname(bot, one["uin"], nick_cache)
    total = (data or {}).get("total") if isinstance(data, dict) else None
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(normalized)
    result.update(
        ok=True,
        items=normalized,
        count=len(normalized),
        total=total,
        text=_qzone_text(normalized),
        raw=data,
    )
    return result


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
        "state": _STATE,
        "store": store,
        "print": print,
        "json": json,
        "time": time,
    }


def _exec_code(code: str, ctx: dict) -> None:
    """执行自定义代码块：上下文键（如循环变量）会直接作为变量暴露。

    写进 ctx 的值只在本次执行内有效；写进 state 的值会落盘、下次触发仍在。
    """
    if not code.strip():
        return
    scope = _code_scope(ctx)
    for k, v in ctx.items():
        if isinstance(k, str) and k.isidentifier():
            scope.setdefault(k, v)
    try:
        compiled = compile(code, f"<visual-plugin:{PLUGIN_MODULE}>", "exec")
    except SyntaxError as exc:
        # 语法错误在「更新插件」时就会被拦下；这里是兜底，给出能定位的信息
        where = "第 {} 行 {}".format(exc.lineno or "?", exc.msg)
        snippet = (exc.text or "").strip()
        nonebot.logger.warning(
            "[可视化插件] 自定义代码语法错误：{}{}",
            where,
            f"（{snippet[:60]}）" if snippet else "",
        )
        raise ValueError(f"自定义代码语法错误：{where}") from None
    try:
        exec(compiled, scope)
    finally:
        _state_save()


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


_WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _schedule_next(cfg: dict, now: Optional[datetime.datetime] = None) -> float:
    """计算距离下一次触发的秒数：支持多个时间点、多个星期、每月某日。"""
    mode = cfg.get("mode") or "interval"
    if mode == "interval":
        try:
            return float(max(1, int(cfg.get("interval", 60))))
        except (TypeError, ValueError):
            return 60.0
    now = now or datetime.datetime.now()
    times = cfg.get("times") or [(9, 0)]
    weekdays = cfg.get("weekdays") or []
    try:
        day = int(cfg.get("day", 1))
    except (TypeError, ValueError):
        day = 1
    best: Optional[float] = None
    for offset in range(0, 370):
        d = now + datetime.timedelta(days=offset)
        if mode == "weekly" and weekdays and d.weekday() not in weekdays:
            continue
        if mode == "monthly":
            last = calendar.monthrange(d.year, d.month)[1]
            if d.day != min(day, last):
                continue
        for hour, minute in times:
            candidate = d.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if candidate <= now:
                continue
            delta = (candidate - now).total_seconds()
            if best is None or delta < best:
                best = delta
    return max(1.0, best if best is not None else 60.0)


def _trigger_info(cfg: dict, run_count: int = 0) -> dict:
    """定时任务触发时注入的上下文：时间、日期、星期、触发方式、第几次。"""
    now = datetime.datetime.now()
    return {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "clock": now.strftime("%H:%M"),
        "weekday": _WEEKDAY_NAMES[now.weekday()],
        "weekday_index": now.weekday(),
        "mode": cfg.get("mode") or "interval",
        "run_count": run_count,
    }


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
    elif ntype == "storage":
        action = str(cfg.get("action") or "set").strip().lower()
        key = cfg.get("key", "")
        value = cfg.get("value", "")
        fallback = cfg.get("fallback", "")
        json_mode = bool(cfg.get("json", False))
        var = (cfg.get("var") or "store").strip() or "store"
        key_expr = f"_tpl({_py_literal(key)}, ctx)"
        if action == "get":
            lines.append(
                f"    ctx[{_py_literal(var)}] = _store_node('get', {key_expr}, None, False, "
                f"_store_expr({_py_literal(fallback)}, ctx, {_py_literal(json_mode)}))"
            )
        elif action == "keys":
            lines.append(f"    ctx[{_py_literal(var)}] = _store_node('keys', {key_expr})")
        elif action in ("set", "append"):
            lines.append(
                f"    _store_node({_py_literal(action)}, {key_expr}, "
                f"_store_expr({_py_literal(value)}, ctx, {_py_literal(json_mode)}), False)"
            )
        elif action == "incr":
            lines.append(
                f"    _store_node('incr', {key_expr}, "
                f"_store_expr({_py_literal(value)}, ctx, False))"
            )
        elif action == "delete":
            lines.append(f"    _store_node('delete', {key_expr}, None, False)")
        else:
            lines.append(f"    _store_node('clear', {key_expr}, None, False)")
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
    elif ntype == "qzone":
        var = (cfg.get("var") or "qzone").strip() or "qzone"
        lines.append(f"    ctx[{_py_literal(var)}] = await _qzone_fetch(ctx, {_py_literal(cfg)})")
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


def _schedule_cfg_literal(cfg: dict) -> str:
    """把定时任务配置规整为生成代码里的字面量（兼容旧的 time / weekday 单值字段）。"""
    mode = str(cfg.get("mode") or "interval").strip().lower()
    if mode not in ("interval", "daily", "weekly", "monthly"):
        mode = "interval"
    try:
        interval = max(1, min(86400, int(cfg.get("interval", 60))))
    except (TypeError, ValueError):
        interval = 60
    raw_times = cfg.get("times")
    if not isinstance(raw_times, list) or not raw_times:
        raw_times = [cfg.get("time") or "09:00"]
    times = sorted({_parse_time(str(t)) for t in raw_times if str(t).strip()}) or [(9, 0)]
    raw_weekdays = cfg.get("weekdays")
    if not isinstance(raw_weekdays, list) or not raw_weekdays:
        raw_weekdays = [cfg.get("weekday", 1)]
    weekdays: List[int] = []
    for item in raw_weekdays:
        try:
            weekdays.append(min(6, max(0, int(item))))
        except (TypeError, ValueError):
            continue
    try:
        day = max(1, min(31, int(cfg.get("day", 1))))
    except (TypeError, ValueError):
        day = 1
    return _py_literal(
        {
            "mode": mode,
            "interval": interval,
            "times": times,
            "weekdays": sorted(set(weekdays)) or [0],
            "day": day,
            "run_on_start": bool(cfg.get("run_on_start", False)),
        }
    )


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
            sections.append(
                f"""# ---------- 定时任务 ----------
driver = get_driver()
_SCHEDULE_{nid} = {_schedule_cfg_literal(cfg)}


@driver.on_startup
async def _schedule_{nid}():
    async def _task():
        _runs = 0
        _first = True
        while True:
            if not (_first and _SCHEDULE_{nid}.get("run_on_start")):
                await asyncio.sleep(_schedule_next(_SCHEDULE_{nid}))
            _first = False
            _runs += 1
            try:
                nonebot.logger.info(
                    f"[可视化插件] 定时任务触发：{{PLUGIN_NAME}}（第 {{_runs}} 次）"
                )
                ctx = _build_ctx(None, None)
                ctx["trigger"] = _trigger_info(_SCHEDULE_{nid}, _runs)
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


# 自定义代码里最容易出现的「跨语法」写法（把模板的点路径当成 Python）
_CODE_HINTS = (
    (re.compile(r"(?<![0-9])\.\d+"), "Python 取列表元素要写 x[0]，不支持模板那种 x.0 写法"),
    (re.compile(r"\{\{"), "代码里不做 {{}} 插值，取上游值直接写变量名或 ctx['名']"),
)


def _code_hint(code: str, lineno: Optional[int]) -> str:
    """针对出错那一行给出针对性提示，命中才返回。"""
    if not lineno:
        return ""
    lines = code.splitlines()
    if not 1 <= lineno <= len(lines):
        return ""
    text = lines[lineno - 1]
    for pattern, hint in _CODE_HINTS:
        if pattern.search(text):
            return f"；提示：{hint}"
    return ""


def _check_code_nodes(flow: dict) -> None:
    """生成前先编译自定义代码，把语法错误挡在「更新插件」这一步。

    运行时才报 SyntaxError 的话，日志里只有「定时任务异常：invalid syntax（<visual-plugin:xxx>, line 1）」，
    既看不出是哪个节点、也看不出哪一行，排错成本很高。
    """
    for node in flow.get("nodes") or []:
        if node.get("type") != "code":
            continue
        code = ((node.get("config") or {}).get("code") or "").strip()
        if not code:
            continue
        try:
            compile(code, "<自定义代码>", "exec")
        except SyntaxError as exc:
            snippet = (exc.text or "").strip()
            where = f"第 {exc.lineno} 行" if exc.lineno else ""
            detail = f"{where} {exc.msg}".strip()
            if snippet:
                detail += f"（{snippet[:60]}）"
            raise ValueError(
                f"节点 {node.get('id')} 的自定义代码有语法错误：{detail}"
                + _code_hint(code, exc.lineno)
            ) from None


def generate_code(plugin: VisualPlugin, bot_name: str = "") -> str:
    """把可视化流程编译为直接控制流的 OneBot V11 NoneBot 插件源码。"""
    flow = _migrate_flow(plugin.flow)
    _validate_flow(flow, require_entry=True)
    _check_code_nodes(flow)
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
    removed = remove_plugin_files(bot_id, plugin.module)
    plugins = [VisualPlugin(**p) for p in list_visual_plugins()]
    target_p = next((p for p in plugins if p.id == plugin_id), None)
    if target_p is not None:
        target_p.installed = [e for e in target_p.installed if e.get("bot_id") != bot_id]
        target_p.updated_at = _now()
        _save_all(plugins)
    return {"removed": removed, "module": plugin.module}
