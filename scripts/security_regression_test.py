"""安全回归测试：验证代码生成注入防护、更新数据保护、登录限流与接口校验。

用法：.venv\\Scripts\\python.exe scripts\\security_regression_test.py
"""

from __future__ import annotations

import ast
import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail and not cond else ""))
    if not cond:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# 1. 可视化插件生成器代码注入防护
# ---------------------------------------------------------------------------

from backend.models import BotUpdate  # noqa: E402
from backend.visual_plugin import VisualPlugin, generate_code  # noqa: E402


def _flow_with_entry() -> dict:
    return {
        "nodes": [
            {
                "id": "a",
                "type": "listener_group",
                "config": {"groups": "all", "keywords": "", "match": "contains", "at_me": False},
            },
            {
                "id": "b",
                "type": "send",
                "config": {"mode": "finish", "target": {"type": "event", "id": ""}, "messages": []},
            },
        ],
        "edges": [{"from": "a", "port": "next", "to": "b"}],
    }


payload = 'x"\nimport os\nos.system("calc")\n#'

# 1.1 循环变量名：非法标识符必须被拒绝
flow_bad_var = {
    "nodes": [
        {
            "id": "a",
            "type": "listener_group",
            "config": {"groups": "all", "keywords": "", "match": "contains", "at_me": False},
        },
        {
            "id": "b",
            "type": "loop",
            "config": {"items": "[1]", "var": "item in [1]:\n    import os\n    pass", "end": ""},
        },
    ],
    "edges": [{"from": "a", "port": "next", "to": "b"}],
}
try:
    generate_code(VisualPlugin(id="p1", name="p", module="vplugin_p1", flow=flow_bad_var))
    check("循环变量名注入被拒绝", False, "未抛异常")
except ValueError:
    check("循环变量名注入被拒绝", True)

# 1.2 合法循环变量名仍可生成
flow_good_var = _flow_with_entry()
flow_good_var["nodes"][1] = {
    "id": "b",
    "type": "loop",
    "config": {"items": "[1]", "var": "item_1", "end": ""},
}
flow_good_var["edges"] = [{"from": "a", "port": "next", "to": "b"}]
try:
    code = generate_code(VisualPlugin(id="p2", name="p", module="vplugin_p2", flow=flow_good_var))
    check("合法循环变量名可生成", "for item_1 in" in code and bool(ast.parse(code)))
except ValueError as exc:
    check("合法循环变量名可生成", False, str(exc))

# 1.3 机器人名注入：生成代码必须转义且不含 payload


def _string_constant(code: str, name: str):
    """返回生成代码中顶层赋值 name = "..." 的字符串值，找不到返回 None。"""
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return None


code = generate_code(
    VisualPlugin(id="p3", name="正常插件", module="vplugin_p3", flow=_flow_with_entry()),
    bot_name=payload,
)
check("机器人名注入被转义为字符串", _string_constant(code, "BOT_NAME") == payload and bool(ast.parse(code)))

# 1.4 插件名注入：生成代码必须转义且不含 payload
code = generate_code(
    VisualPlugin(id="p4", name=payload, module="vplugin_p4", flow=_flow_with_entry()),
    bot_name="safe_bot",
)
check("插件名注入被转义为字符串", _string_constant(code, "PLUGIN_NAME") == payload and bool(ast.parse(code)))

# 1.5 正常名称生成正常
code = generate_code(
    VisualPlugin(id="p5", name="天气助手", module="vplugin_p5", flow=_flow_with_entry()),
    bot_name="demo-bot",
)
check("正常名称生成正常", "os.system" not in code and bool(ast.parse(code)))

# 1.6 群号/QQ 号必须为数字或 all
flow_bad_groups = _flow_with_entry()
flow_bad_groups["nodes"][0]["config"]["groups"] = "abc,123"
try:
    generate_code(VisualPlugin(id="p6", name="p", module="vplugin_p6", flow=flow_bad_groups))
    check("非法群号被拒绝", False, "未抛异常")
except ValueError:
    check("非法群号被拒绝", True)

# 1.7 变量名相关字段（collect/api/choice/webhook）校验
for ntype, cfg in [
    ("collect", {"key": "bad key", "prompt": ""}),
    ("api", {"var": "bad var", "url": "", "method": "GET"}),
    ("choice", {"var": "bad var", "options": []}),
    ("listener_webhook", {"var": "bad var", "path": "/x"}),
]:
    flow = {
        "nodes": [
            {"id": "a", "type": "listener_group", "config": {"groups": "all", "keywords": "", "match": "contains", "at_me": False}},
            {"id": "b", "type": ntype, "config": cfg},
        ],
        "edges": [{"from": "a", "port": "next", "to": "b"}],
    }
    try:
        generate_code(VisualPlugin(id="p7", name="p", module="vplugin_p7", flow=flow))
        check(f"{ntype} 非法变量名被拒绝", False)
    except ValueError:
        check(f"{ntype} 非法变量名被拒绝", True)

# ---------------------------------------------------------------------------
# 2. BotUpdate 校验
# ---------------------------------------------------------------------------

try:
    BotUpdate(port=999999)
    check("PATCH 端口越界被拒绝", False)
except Exception:
    check("PATCH 端口越界被拒绝", True)

try:
    BotUpdate(name='x"y')
    check("PATCH 名称含引号被拒绝", False)
except Exception:
    check("PATCH 名称含引号被拒绝", True)

try:
    BotUpdate(port=8080, name="ok-bot")
    check("PATCH 合法字段通过", True)
except Exception as exc:
    check("PATCH 合法字段通过", False, str(exc))

# ---------------------------------------------------------------------------
# 3. 登录限流
# ---------------------------------------------------------------------------

from backend.security import (  # noqa: E402
    clear_login_failures,
    is_login_blocked,
    record_login_failure,
)

clear_login_failures("test:admin")
check("限流初始未触发", not is_login_blocked("test:admin"))
for _ in range(5):
    record_login_failure("test:admin")
check("5 次失败后触发限流", is_login_blocked("test:admin"))
clear_login_failures("test:admin")
check("清除失败记录后恢复", not is_login_blocked("test:admin"))

# ---------------------------------------------------------------------------
# 4. 更新脚本：受保护条目拒绝覆盖 + 校验和
# ---------------------------------------------------------------------------

import update as update_mod  # noqa: E402
from update import apply_update, sha256, verify_checksum  # noqa: E402


def _build_pkg(zf: zipfile.ZipFile, req: str = "fastapi", extra: tuple[str, ...] = ()) -> None:
    zf.writestr("install.py", "x")
    zf.writestr("start.py", "new-start")
    zf.writestr("backend/main.py", "new-main")
    zf.writestr("frontend/dist/index.html", "new-index")
    zf.writestr("requirements.txt", req)
    for p in extra:
        zf.writestr(p, "boom")


with tempfile.TemporaryDirectory(prefix="nbwebui_reg_") as tmp:
    tmp_path = Path(tmp)
    fake_root = tmp_path / "root"
    (fake_root / "data").mkdir(parents=True)
    (fake_root / ".venv").mkdir(parents=True)
    (fake_root / "data" / "users.json").write_text('{"admin": 1}', encoding="utf-8")
    (fake_root / ".venv" / "marker").write_text("keep", encoding="utf-8")
    (fake_root / "requirements.txt").write_text("fastapi", encoding="utf-8")
    (fake_root / "start.py").write_text("old", encoding="utf-8")

    old_root, old_log = update_mod.ROOT, update_mod.LOG_FILE
    update_mod.ROOT = fake_root
    update_mod.LOG_FILE = fake_root / "update.log"
    try:
        # 4.1 恶意发布包（含 data/）必须被拒绝，且 data/.venv 不受影响
        bad_buf = io.BytesIO()
        with zipfile.ZipFile(bad_buf, "w") as zf:
            _build_pkg(zf, extra=("data/evil.txt",))
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(bad_buf.getvalue())
        try:
            apply_update(bad_zip)
            check("含 data/ 的发布包被拒绝", False)
        except RuntimeError as exc:
            check("含 data/ 的发布包被拒绝", "受保护" in str(exc), str(exc))
        check("data/ 未被破坏", (fake_root / "data" / "users.json").exists())
        check(".venv 未被破坏", (fake_root / ".venv" / "marker").exists())

        # 4.2 正常发布包可更新且保留 data/.venv
        good_buf = io.BytesIO()
        with zipfile.ZipFile(good_buf, "w") as zf:
            _build_pkg(zf)
        good_zip = tmp_path / "good.zip"
        good_zip.write_bytes(good_buf.getvalue())
        apply_update(good_zip)
        check("正常发布包更新成功", (fake_root / "start.py").read_text(encoding="utf-8") == "new-start")
        check("更新后 data/ 保留", (fake_root / "data" / "users.json").exists())
        check("更新后 .venv 保留", (fake_root / ".venv" / "marker").exists())

        # 4.3 校验和：匹配通过 / 不匹配拒绝 / 缺失跳过
        pkg = tmp_path / "pkg.bin"
        pkg.write_bytes(b"hello")
        digest = sha256(pkg)
        (tmp_path / "pkg.bin.sha256").write_text(f"{digest}  pkg.bin", encoding="utf-8")
        verify_checksum(pkg.as_uri(), pkg)
        check("校验和匹配通过", True)
        (tmp_path / "pkg.bin.sha256").write_text("0" * 64 + "  pkg.bin", encoding="utf-8")
        try:
            verify_checksum(pkg.as_uri(), pkg)
            check("校验和不匹配被拒绝", False)
        except RuntimeError:
            check("校验和不匹配被拒绝", True)
        (tmp_path / "pkg.bin.sha256").unlink()
        verify_checksum(pkg.as_uri(), pkg)
        check("校验文件缺失时跳过", True)
    finally:
        update_mod.ROOT = old_root
        update_mod.LOG_FILE = old_log

print("\n全部安全回归测试通过")
