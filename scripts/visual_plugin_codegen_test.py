"""可视化插件代码生成回归测试（纯标准库，不需要启动服务）。

覆盖：
- 定时任务定点触发的时间计算（今天尚未到点时应当命中今天，而不是推迟一天）；
- 定时任务 / WebHook 触发分支能解析到 Bot，从而真正发出消息；
- 定时任务后台任务持有引用，并记录触发日志。

用法：.venv\\Scripts\\python.exe scripts\\visual_plugin_codegen_test.py
"""

from __future__ import annotations

import calendar
import datetime
import sys
from pathlib import Path
from typing import Optional

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
    """取出 _RUNTIME_TEMPLATE 的字符串内容（即写入机器人的运行时骨架）。"""
    marker = "_RUNTIME_TEMPLATE = '''\\\n"
    start = text.index(marker) + len(marker)
    end = text.index("\n'''", start)
    return text[start:end]


def load_seconds_until(template: str):
    """单独执行模板里的 _seconds_until，便于用固定时间验证行为。"""
    start = template.index("def _seconds_until(")
    end = template.index("\n\n\n@event_preprocessor", start)
    namespace: dict = {
        "datetime": _FakeDatetimeModule,
        "calendar": calendar,
        "Optional": Optional,
    }
    exec(compile(template[start:end] + "\n", "<runtime_template>", "exec"), namespace)
    return namespace["_seconds_until"]


def main() -> int:
    text = GENERATOR.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    template = load_template(text)
    seconds_until = load_seconds_until(template)

    # 1. 定点触发的时间计算
    _FixedNow.value = datetime.datetime(2026, 1, 5, 8, 0, 0)  # 周一 08:00
    check(
        "每天定点：今天尚未到点只等 1 小时",
        seconds_until(9, 0) == 3600.0,
        f"实际 {seconds_until(9, 0)}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 10, 0, 0)
    check(
        "每天定点：今天已过点则等明天",
        seconds_until(9, 0) == 82800.0,
        f"实际 {seconds_until(9, 0)}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 8, 0, 0)
    check(
        "每周定点：今天正是目标星期且未到点只等 1 小时",
        seconds_until(9, 0, weekday=0) == 3600.0,
        f"实际 {seconds_until(9, 0, weekday=0)}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 10, 0, 0)
    check(
        "每周定点：今天已过点则等下周",
        seconds_until(9, 0, weekday=0) == 601200.0,
        f"实际 {seconds_until(9, 0, weekday=0)}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 5, 8, 0, 0)
    check(
        "每月定点：本月目标日未到按本月算",
        seconds_until(9, 0, day=10) == 435600.0,
        f"实际 {seconds_until(9, 0, day=10)}",
    )
    _FixedNow.value = datetime.datetime(2026, 1, 31, 10, 0, 0)
    check(
        "每月定点：小月自动按月末算",
        seconds_until(9, 0, day=31) == 2415600.0,
        f"实际 {seconds_until(9, 0, day=31)}",
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
            "生成代码：每天定点使用 _seconds_until",
            "await asyncio.sleep(_seconds_until(9, 0))" in code,
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
            "ctx = _build_ctx(None, None)\n                _attach_bot(ctx)" in code,
        )

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 40)
    print(f"通过 {len(results) - len(failed)}/{len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
