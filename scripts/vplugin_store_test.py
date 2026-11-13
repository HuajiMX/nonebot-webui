"""可视化插件「数据存储」面板侧读写测试。

覆盖：读写单个键、保留机器人或别的操作写入的键、删除、清空、
非法键名与非法模块名的拦截、容量上限，以及机器人进程写的结构能被面板正确解析。

用法：.venv\\Scripts\\python.exe scripts\\vplugin_store_test.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import vplugin_store  # noqa: E402
from backend.bot_manager import bot_manager  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    suffix = f" - {detail}" if detail and not cond else ""
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{suffix}")


class _FakeBot:
    def __init__(self, directory: Path):
        self.directory = str(directory)


def main() -> int:
    module = "vplugin_ab12cd34ef"

    with tempfile.TemporaryDirectory() as tmp:
        bot_dir = Path(tmp) / "bot"
        plugin_dir = bot_dir / "plugins"
        plugin_dir.mkdir(parents=True)

        fake = _FakeBot(bot_dir)
        bot_manager.get_bot = lambda bot_id: fake if bot_id == "bot1" else None  # type: ignore[assignment]
        bot_manager.plugin_dir_path = lambda bot: Path(bot.directory) / "plugins"  # type: ignore[assignment]

        data = vplugin_store.read_store("bot1", module)
        check("空存储：文件不存在且无键", data["exists"] is False and data["items"] == [])

        item = vplugin_store.write_key("bot1", module, "count", 1)
        check("写入：返回键信息", item["key"] == "count" and item["json"] == "1")
        check(
            "写入：读回键列表",
            [r["key"] for r in vplugin_store.read_store("bot1", module)["items"]] == ["count"],
        )

        vplugin_store.write_key("bot1", module, "最近推送", [{"tid": "abc"}])
        rows = {r["key"]: r for r in vplugin_store.read_store("bot1", module)["items"]}
        check("中文键可读写", "最近推送" in rows)
        check("列表按 JSON 保存", json.loads(rows["最近推送"]["json"]) == [{"tid": "abc"}])

        # 机器人侧写入的结构（items/键/{v,t}）必须能被面板解析
        path = plugin_dir / f"vplugin_store_{module}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["items"]["from_bot"] = {"v": 42, "t": "2026-11-13 10:00:00"}
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        rows = {r["key"]: r for r in vplugin_store.read_store("bot1", module)["items"]}
        check("能读机器人写入的键", rows["from_bot"]["preview"] == "42")

        vplugin_store.write_key("bot1", module, "mine", "x")
        keys = {r["key"] for r in vplugin_store.read_store("bot1", module)["items"]}
        check("写入不会丢其它键", {"count", "最近推送", "from_bot", "mine"} <= keys)

        check("删除存在的键", vplugin_store.delete_key("bot1", module, "mine") is True)
        check("删除不存在的键返回 False", vplugin_store.delete_key("bot1", module, "mine") is False)

        for bad in ("", "a.b", "x" * 65, "含 空格"):
            try:
                vplugin_store.write_key("bot1", module, bad, 1)
                rejected = False
            except vplugin_store.StoreError:
                rejected = True
            check(f"拒绝非法键名 {bad[:6]!r}", rejected)

        for bad_module in ("../evil", "vplugin_../../x", ""):
            try:
                vplugin_store.read_store("bot1", bad_module)
                rejected = False
            except vplugin_store.StoreError:
                rejected = True
            check(f"拒绝非法模块名 {bad_module!r}", rejected)

        try:
            vplugin_store.read_store("nope", module)
            rejected = False
        except vplugin_store.StoreError:
            rejected = True
        check("机器人不存在时报错", rejected)

        count = vplugin_store.clear_store("bot1", module)
        check("清空返回被删键数", count >= 3)
        check("清空后为空", vplugin_store.read_store("bot1", module)["count"] == 0)

        oversize = "x" * (vplugin_store.STORE_LIMIT_BYTES + 100)
        try:
            vplugin_store.write_key("bot1", module, "huge", oversize)
            rejected = False
        except vplugin_store.StoreError:
            rejected = True
        check("超过容量上限时拒绝写入", rejected)
        check(
            "拒绝后不留下半截数据",
            vplugin_store.read_store("bot1", module)["count"] == 0,
        )

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 40)
    print(f"通过 {len(results) - len(failed)}/{len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
