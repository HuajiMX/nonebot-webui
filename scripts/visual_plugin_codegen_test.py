"""可视化插件代码生成回归测试（纯标准库，不需要启动服务）。

覆盖：
- 定时任务定点触发的时间计算（今天尚未到点时应当命中今天，而不是推迟一天）；
- 定时任务 / WebHook 触发分支能解析到 Bot，从而真正发出消息；
- 定时任务后台任务持有引用，并记录触发日志；
- 「数据存储」的读写、追加、自增、删除、清空，以及重启后仍在、外部改动可感知。

用法：.venv\\Scripts\\python.exe scripts\\visual_plugin_codegen_test.py
"""

from __future__ import annotations

import calendar
import datetime
import ast
import json
import os
import re
import sys
import tempfile
import threading
import time
import types
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "backend" / "visual_plugin.py"

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    suffix = f" - {detail}" if detail and not cond else ""
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{suffix}")


class _FixedNow:
    """替身 datetime 类：now() 返回固定时刻。"""

    value = datetime.datetime(2026, 1, 5, 8, 0, 0)  # 周一 08:00

    @classmethod
    def now(cls, tz=None):
        return cls.value


class _FakeDatetimeModule:
    """替身 datetime 模块，用于给模板里的 _seconds_until 注入固定时间。"""


# 在类体外赋值：类体内写 datetime.timedelta 会解析到上面刚定义的类属性 _FixedNow
_FakeDatetimeModule.datetime = _FixedNow
_FakeDatetimeModule.timedelta = datetime.timedelta


def load_template(text: str) -> str:
    """取出 _RUNTIME_TEMPLATE 解析后的字符串内容（即写入机器人的运行时骨架）。

    用 ast 取常量值而不是切原文：模板里有 r"..." 与转义，只有解析后的内容
    才和真实生成的代码一致，否则存储正则这类断言会判错。
    """
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_RUNTIME_TEMPLATE":
                    return ast.literal_eval(node.value)
    raise ValueError("未找到 _RUNTIME_TEMPLATE")


def load_schedule_next(template: str):
    """单独执行模板里的 _schedule_next，便于用固定时间验证行为。"""
    start = template.index("def _schedule_next(")
    end = template.index("\n\ndef _trigger_info(", start)
    namespace: dict = {
        "datetime": _FakeDatetimeModule,
        "calendar": calendar,
        "Optional": Optional,
    }
    exec(compile(template[start:end] + "\n", "<runtime_template>", "exec"), namespace)
    return namespace["_schedule_next"]


class _FakeLogger:
    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def load_store_runtime(template: str) -> str:
    """取出模板里的存储实现（不含事件处理器），便于脱离 nonebot 单独测试。"""
    start = template.index("# ---------- 长期存储")
    end = template.index("\n\n\n_SAFE_BUILTINS = {", start)
    return template[start:end]


def exec_store_runtime(template: str, plugin_dir: Path, module: str = "vplugin_storetest") -> dict:
    """在一个独立命名空间里跑一遍存储实现，相当于机器人进程启动时导入插件。"""
    namespace: dict = {
        "PLUGIN_MODULE": module,
        "__file__": str(plugin_dir / f"{module}.py"),
        "nonebot": types.SimpleNamespace(logger=_FakeLogger()),
        "os": os,
        "json": json,
        "re": re,
        "datetime": datetime,
        "threading": threading,
        "Dict": Dict,
        "Any": Any,
    }
    exec(compile(load_store_runtime(template), "<store_runtime>", "exec"), namespace)
    return namespace


def raises(func) -> bool:
    try:
        func()
    except Exception:  # noqa: BLE001
        return True
    return False


def test_store_runtime(template: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        ns = exec_store_runtime(template, plugin_dir)
        store = ns["store"]

        store.set("count", 1)
        check("存储：写入后能读回", store.get("count") == 1)
        store.incr("count")
        check("存储：自增累加", store.get("count") == 2)
        store.append("list", {"a": 1})
        store.append("list", {"a": 2})
        check("存储：追加保留顺序", [x["a"] for x in store.get("list")] == [1, 2])
        check("存储：按前缀列出键", store.keys("co") == ["count"])
        check("存储：contains 判断", "count" in store)
        store.delete("count")
        check("存储：删除键", store.get("count", "gone") == "gone")
        check("存储：键名含点号时报错", raises(lambda: store.set("a.b", 1)))
        check("存储：键名为空时报错", raises(lambda: store.set("", 1)))

        # 重新跑一遍存储实现 = 机器人重启后重新加载插件
        ns2 = exec_store_runtime(template, plugin_dir)
        check(
            "存储：重启后数据仍在",
            ns2["store"].get("list") == [{"a": 1}, {"a": 2}],
        )

        # 模拟面板改文件：运行时靠 mtime 感知，不能拿旧内存覆盖
        path = plugin_dir / "vplugin_store_vplugin_storetest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["items"]["panel_key"] = {"v": "from-panel", "t": "2026-11-13 16:00:00"}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.utime(path, (time.time() + 5, time.time() + 5))
        check(
            "存储：外部改动后能读到最新值",
            ns2["store"].get("panel_key") == "from-panel",
        )

        ns2["store"].clear()
        check("存储：清空后为空", ns2["store"].keys() == [])


def main() -> int:
    text = GENERATOR.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    template = load_template(text)
    schedule_next = load_schedule_next(template)

    # 1. 定点触发的时间计算
    check(
        "间隔模式：按配置秒数等待",
        schedule_next({"mode": "interval", "interval": 90}) == 90.0,
        f"实际 {schedule_next({'mode': 'interval', 'interval': 90})}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 8, 0, 0)  # 周一 08:00
    check(
        "每天定点：今天尚未到点只等 1 小时",
        schedule_next({"mode": "daily", "times": [(9, 0)]}) == 3600.0,
        f"实际 {schedule_next({'mode': 'daily', 'times': [(9, 0)]})}",
    )
    check(
        "多个时间点：取最近的一个",
        schedule_next({"mode": "daily", "times": [(9, 0), (12, 30)]}) == 3600.0,
        f"实际 {schedule_next({'mode': 'daily', 'times': [(9, 0), (12, 30)]})}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 10, 0, 0)
    check(
        "每天定点：今天已过点则等明天",
        schedule_next({"mode": "daily", "times": [(9, 0)]}) == 82800.0,
        f"实际 {schedule_next({'mode': 'daily', 'times': [(9, 0)]})}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 8, 0, 0)
    check(
        "每周定点：今天正是目标星期且未到点只等 1 小时",
        schedule_next({"mode": "weekly", "times": [(9, 0)], "weekdays": [0]}) == 3600.0,
        f"实际 {schedule_next({'mode': 'weekly', 'times': [(9, 0)], 'weekdays': [0]})}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 10, 0, 0)
    check(
        "每周定点：今天已过点则等下周",
        schedule_next({"mode": "weekly", "times": [(9, 0)], "weekdays": [0]}) == 601200.0,
        f"实际 {schedule_next({'mode': 'weekly', 'times': [(9, 0)], 'weekdays': [0]})}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 8, 0, 0)
    check(
        "每月定点：本月目标日未到按本月算",
        schedule_next({"mode": "monthly", "times": [(9, 0)], "day": 10}) == 435600.0,
        f"实际 {schedule_next({'mode': 'monthly', 'times': [(9, 0)], 'day': 10})}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 31, 10, 0, 0)
    check(
        "每月定点：小月自动按月末算",
        schedule_next({"mode": "monthly", "times": [(9, 0)], "day": 31}) == 2415600.0,
        f"实际 {schedule_next({'mode': 'monthly', 'times': [(9, 0)], 'day': 31})}",
    )

    # 2. 运行时骨架：定时任务 / WebHook 触发也能发出消息
    check("运行时骨架包含 Bot 解析函数", "def _resolve_bot(" in template)
    check(
        "发送消息经由 _resolve_bot 取 Bot",
        "bot = _resolve_bot(ctx)" in template and "nonebot.get_bots()" in template,
    )
    check(
        "定时任务/WebHook 选「回复触发者」时给出明确告警",
        'if target == "event" and event is None:' in template,
    )
    check("定点触发计算从今天开始", "for offset in range(0, 370):" in template)
    check(
        "发送目标缺少群号/QQ 号时给出告警",
        "发送消息失败：未指定群号" in template and "发送消息失败：未指定 QQ 号" in template,
    )
    check(
        "运行时骨架包含后台任务助手",
        "def _spawn(coro)" in template and "asyncio.create_task(coro)" in template,
    )
    check(
        "无事件触发分支补齐 Bot 与 bot_id",
        "def _attach_bot(ctx: dict) -> None:" in template
        and 'ctx["bot_id"] = bot.self_id' in template,
    )
    check(
        "运行时骨架包含长期存储实现",
        "class _StoreProxy" in template
        and "def _store_set(" in template
        and "def _store_append(" in template,
    )
    check("存储键名禁止点号", "STORE_KEY_RE" in template)
    check(
        "存储写入走文件锁与原子替换",
        "class _StoreFileLock" in template and "os.replace(path + \".tmp\", path)" in template,
    )

    # 2.1 存储行为（脱离 nonebot 单独跑模板里的实现）
    test_store_runtime(template)

    # 3. 生成的插件代码（需要 WebUI 依赖）
    sys.path.insert(0, str(ROOT))
    try:
        from backend.visual_plugin import VisualPlugin, generate_code
    except Exception as exc:  # noqa: BLE001
        check("导入生成器（需要 WebUI 依赖）", False, str(exc))
        VisualPlugin = generate_code = None  # type: ignore[assignment]

    if generate_code is not None:
        plugin = VisualPlugin(
            id="codegen-test",
            name="定时任务测试",
            module="vplugin_test",
            flow={
                "nodes": [
                    {
                        "id": "sch1",
                        "type": "schedule",
                        "config": {
                            "mode": "daily",
                            "interval": 60,
                            "time": "09:00",
                            "weekday": 1,
                            "day": 1,
                        },
                    },
                    {
                        "id": "send1",
                        "type": "send",
                        "config": {
                            "mode": "finish",
                            "target": {"type": "group", "id": "123456"},
                            "messages": [{"type": "text", "value": "定时打卡"}],
                        },
                    },
                ],
                "edges": [{"from": "sch1", "to": "send1", "port": "next"}],
            },
        )
        code = generate_code(plugin, bot_name="测试机器人")
        check(
            "生成代码：定时任务用 _schedule_next 计算等待",
            "await asyncio.sleep(_schedule_next(_SCHEDULE_sch1))" in code,
        )
        check(
            "生成代码：定时任务经 _spawn 启动并记录触发日志",
            "_spawn(_task())" in code and "定时任务触发：{PLUGIN_NAME}" in code,
        )
        check(
            "生成代码：下游发送步骤可解析 Bot",
            "bot = _resolve_bot(ctx)" in code and "await _step_send1(ctx)" in code,
        )
        check(
            "生成代码：定时任务入口补齐 Bot",
            'ctx = _build_ctx(None, None)' in code
            and 'ctx["trigger"] = _trigger_info(' in code
            and "                _attach_bot(ctx)" in code,
        )

        store_plugin = VisualPlugin(
            id="store-test",
            name="存储测试",
            module="vplugin_store_gen",
            flow={
                "nodes": [
                    {"id": "sch1", "type": "schedule", "config": {"mode": "interval", "interval": 60}},
                    {"id": "st1", "type": "storage", "config": {"action": "incr", "key": "total", "value": "1"}},
                    {
                        "id": "st2",
                        "type": "storage",
                        "config": {"action": "get", "key": "total", "var": "n", "fallback": "0"},
                    },
                    {
                        "id": "st3",
                        "type": "storage",
                        "config": {"action": "append", "key": "tids", "value": "{{tid}}", "json": True},
                    },
                    {"id": "st4", "type": "storage", "config": {"action": "clear", "key": ""}},
                ],
                "edges": [
                    {"from": "sch1", "to": "st1", "port": "next"},
                    {"from": "st1", "to": "st2", "port": "next"},
                    {"from": "st2", "to": "st3", "port": "next"},
                    {"from": "st3", "to": "st4", "port": "next"},
                ],
            },
        )
        store_code = generate_code(store_plugin, bot_name="测试机器人")
        compiled = True
        try:
            compile(store_code, "<store-plugin>", "exec")
        except SyntaxError:
            compiled = False
        check("生成代码：含存储节点的插件可编译", compiled)
        check(
            "生成代码：自增调用",
            "_store_node('incr', _tpl('total', ctx), _store_expr('1', ctx, False))" in store_code,
        )
        check("生成代码：读取结果写入变量", "ctx['n'] = _store_node('get'" in store_code)
        check(
            "生成代码：追加保留原值（不转字符串）",
            "_store_expr('{{tid}}', ctx, True)" in store_code,
        )
        check("生成代码：清空可不填键名", "_store_node('clear', _tpl('', ctx)" in store_code)

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 40)
    print(f"通过 {len(results) - len(failed)}/{len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
