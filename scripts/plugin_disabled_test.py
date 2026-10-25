"""插件暂停回归测试：暂停后插件源码必须离开 NoneBot 的扫描目录。

覆盖：
- 暂停把 .py 插件移入 .webui_disabled/，NoneBot（pkgutil.iter_modules）不再发现它，
  因此插件里的定时任务不会再被注册/触发（不依赖机器人入口是否读取禁用清单）；
- 启用把源码移回插件目录，暂停清单同步更新；
- 历史数据（只有 webui_disabled_plugins.json、文件还在）自动迁移；
- 插件包（目录 + __init__.py）同样支持暂停/启用；
- 暂停期间覆盖安装保持暂停；删除插件时隔离目录里的副本一起清理。

用法：.venv\\Scripts\\python.exe scripts\\plugin_disabled_test.py
"""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="nbwebui_plugin_disabled_"))
os.environ["NB_WEBUI_DATA"] = str(TMP / "data")

from backend.bot_manager import bot_manager  # noqa: E402
from backend import plugin_manager  # noqa: E402
from backend.plugin_manager import (  # noqa: E402
    DISABLED_DIRNAME,
    install_plugin_file,
    list_plugins,
    remove_plugin_files,
    set_plugin_enabled,
)
from backend.models import Bot  # noqa: E402

BOT_ID = "testbot00001"
BOT_DIR = TMP / "bot"
PLUGIN_DIR = BOT_DIR / "src" / "plugins"

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    suffix = f" - {detail}" if detail and not cond else ""
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{suffix}")


def names() -> dict[str, dict]:
    return {p["name"]: p for p in list_plugins(BOT_ID)}


def discovered() -> list[str]:
    """NoneBot 的插件扫描方式：pkgutil.iter_modules(plugin_dir)。"""
    return [m.name for m in pkgutil.iter_modules([str(PLUGIN_DIR)])]


def timer_plugin_source() -> str:
    # 真实可视化插件在模块导入时向 driver.on_startup 注册定时任务；
    # 这里用写标记文件代替（测试环境无需安装 nonebot）。
    return (
        "from pathlib import Path\n\n"
        "PLUGIN_NAME = '定时测试'\n\n"
        "# 导入即注册定时任务（对应生成代码里的 @driver.on_startup）\n"
        "(Path(__file__).parent / 'timer_ran.marker').write_text('imported', encoding='utf-8')\n"
    )


def simulate_nonebot_load() -> list[str]:
    """模拟 NoneBot 加载：导入扫描到的每个插件模块。"""
    loaded: list[str] = []
    sys.path.insert(0, str(PLUGIN_DIR))
    try:
        for info in pkgutil.iter_modules([str(PLUGIN_DIR)]):
            if info.name.startswith("_"):
                continue
            importlib.import_module(info.name)
            loaded.append(info.name)
    finally:
        sys.path.remove(str(PLUGIN_DIR))
        for name in loaded:
            sys.modules.pop(name, None)
    return loaded


def main() -> int:
    # ---------- 准备：一个注册的已有项目（入口不读取禁用清单） ----------
    PLUGIN_DIR.mkdir(parents=True)
    (PLUGIN_DIR / "__init__.py").write_text("", encoding="utf-8")
    (PLUGIN_DIR / "vplugin_timer.py").write_text(timer_plugin_source(), encoding="utf-8")
    (BOT_DIR / "bot.py").write_text(
        "import nonebot\n\nnonebot.init()\nnonebot.load_from_toml('pyproject.toml')\n",
        encoding="utf-8",
    )
    (BOT_DIR / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n\n[tool.nonebot]\nplugin_dirs = ["src/plugins"]\n',
        encoding="utf-8",
    )
    bot_manager.update_bot(
        Bot(
            id=BOT_ID,
            name="回归测试",
            directory=str(BOT_DIR),
            plugin_dir="src/plugins",
            managed=False,
            status="stopped",
        )
    )

    # ---------- 1. 初始状态 ----------
    info = names()
    check("插件初始可见且为启用", info.get("vplugin_timer", {}).get("enabled") is True, str(info))
    check("初始能被 NoneBot 扫描到", "vplugin_timer" in discovered(), str(discovered()))

    # ---------- 2. 暂停 ----------
    set_plugin_enabled(BOT_ID, "vplugin_timer", False)
    check("暂停后插件源码离开插件目录", not (PLUGIN_DIR / "vplugin_timer.py").exists())
    check(
        "暂停后源码位于隔离目录",
        (PLUGIN_DIR / DISABLED_DIRNAME / "vplugin_timer.py").exists(),
        str(list((PLUGIN_DIR / DISABLED_DIRNAME).glob("*"))),
    )
    check("暂停后 NoneBot 扫描不到插件", "vplugin_timer" not in discovered(), str(discovered()))
    check(
        "暂停清单已写入 webui_disabled_plugins.json",
        json.loads((BOT_DIR / "webui_disabled_plugins.json").read_text(encoding="utf-8"))
        == ["vplugin_timer"],
    )
    info = names()
    check(
        "插件仍在列表中并标记为暂停",
        info.get("vplugin_timer", {}).get("disabled") is True,
        str(info.get("vplugin_timer")),
    )
    check("暂停后插件目录不含隔离目录外的源码", discovered() == [], str(discovered()))

    # 关键回归：模拟不读取禁用清单的入口（load_from_toml）加载插件
    loaded = simulate_nonebot_load()
    check("暂停后模拟加载不会导入该插件", loaded == [], str(loaded))
    check(
        "暂停后插件的定时任务注册代码没有被执行",
        not (PLUGIN_DIR / "timer_ran.marker").exists(),
    )

    # ---------- 3. 启用 ----------
    set_plugin_enabled(BOT_ID, "vplugin_timer", True)
    check("启用后源码回到插件目录", (PLUGIN_DIR / "vplugin_timer.py").exists())
    check("启用后隔离目录不再保留副本", not (PLUGIN_DIR / DISABLED_DIRNAME / "vplugin_timer.py").exists())
    check(
        "启用后暂停清单为空",
        json.loads((BOT_DIR / "webui_disabled_plugins.json").read_text(encoding="utf-8")) == [],
    )
    info = names()
    check("启用后列表状态为启用", info.get("vplugin_timer", {}).get("enabled") is True, str(info))
    loaded = simulate_nonebot_load()
    check("启用后可以正常加载插件", loaded == ["vplugin_timer"], str(loaded))
    (PLUGIN_DIR / "timer_ran.marker").unlink(missing_ok=True)

    # ---------- 4. 历史数据迁移：只有 JSON、文件还在 ----------
    (BOT_DIR / "webui_disabled_plugins.json").write_text('["vplugin_timer"]', encoding="utf-8")
    info = names()
    check("历史暂停记录会被自动迁移到隔离目录", not (PLUGIN_DIR / "vplugin_timer.py").exists())
    check(
        "迁移后列表仍标记为暂停",
        info.get("vplugin_timer", {}).get("disabled") is True,
        str(info.get("vplugin_timer")),
    )
    set_plugin_enabled(BOT_ID, "vplugin_timer", True)

    # ---------- 5. 插件包（目录） ----------
    pkg = PLUGIN_DIR / "pkgplug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("PLUGIN_NAME = '包插件'\n", encoding="utf-8")
    set_plugin_enabled(BOT_ID, "pkgplug", False)
    check("插件包暂停后离开插件目录", not pkg.exists())
    check(
        "插件包暂停后位于隔离目录",
        (PLUGIN_DIR / DISABLED_DIRNAME / "pkgplug" / "__init__.py").exists(),
    )
    check("插件包暂停后扫描不到", "pkgplug" not in discovered(), str(discovered()))
    info = names()
    check(
        "插件包暂停状态与类型正确",
        info.get("pkgplug", {}).get("disabled") is True
        and info.get("pkgplug", {}).get("kind") == "package",
        str(info.get("pkgplug")),
    )
    set_plugin_enabled(BOT_ID, "pkgplug", True)
    check("插件包启用后恢复", (pkg / "__init__.py").exists())
    remove_plugin_files(BOT_ID, "pkgplug")
    check("删除插件包会清理源码", not pkg.exists())

    # ---------- 6. 暂停期间覆盖安装保持暂停 ----------
    set_plugin_enabled(BOT_ID, "vplugin_timer", False)
    install_plugin_file(BOT_ID, "vplugin_timer.py", timer_plugin_source().encode("utf-8"))
    check("暂停期间覆盖安装不会让插件回到插件目录", not (PLUGIN_DIR / "vplugin_timer.py").exists())
    check(
        "暂停期间覆盖安装会把新内容放进隔离目录",
        (PLUGIN_DIR / DISABLED_DIRNAME / "vplugin_timer.py").exists(),
    )
    check(
        "覆盖安装后仍被 NoneBot 扫描不到",
        "vplugin_timer" not in discovered(),
        str(discovered()),
    )
    remove_plugin_files(BOT_ID, "vplugin_timer")
    check(
        "删除插件时隔离目录里的副本一起清理",
        not (PLUGIN_DIR / DISABLED_DIRNAME / "vplugin_timer.py").exists(),
    )
    info = names()
    check("删除后插件不再出现在列表", "vplugin_timer" not in info, str(info))

    failed = [name for name, ok, _ in results if not ok]
    print()
    if failed:
        print(f"失败 {len(failed)} 项：{', '.join(failed)}")
        return 1
    print(f"全部通过（{len(results)} 项）")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        bot_manager.remove_bot(BOT_ID)
        shutil.rmtree(TMP, ignore_errors=True)
    raise SystemExit(code)
