"""可视化插件「数据存储」界面冒烟测试（Playwright）。

前置条件：测试服务已启动（默认 127.0.0.1:9520）、管理员 admin/admin123、
存在一个已装配「存储界面测试」插件的机器人。

用法：.venv\\Scripts\\python.exe scripts\\ui_storage_test.py [base_url]
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9520"
OUT = Path(__file__).resolve().parent.parent / ".tmp_uitest" / "shots"
OUT.mkdir(parents=True, exist_ok=True)

results: list[tuple[str, bool]] = []


def check(name: str, cond: bool) -> None:
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE + "/login", wait_until="networkidle")
        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click(".login-btn")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        page.goto(BASE + "/visual-plugins", wait_until="networkidle")
        page.wait_for_selector(".layout", timeout=15000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "01_list.png"), full_page=True)

        data_btn = page.get_by_role("button", name="数据", exact=True)
        check("插件列表出现「数据」按钮", data_btn.count() > 0)
        data_btn.first.click()
        page.wait_for_selector(".el-drawer", timeout=8000)
        page.wait_for_timeout(900)
        drawer = page.locator(".el-drawer")
        check("抽屉标题包含「数据存储」", "数据存储" in drawer.inner_text())
        check("抽屉有「新增键」入口", drawer.get_by_text("新增键").count() > 0)
        page.screenshot(path=str(OUT / "02_drawer_empty.png"))

        drawer.get_by_role("button", name="新增键").click()
        dialog = page.locator(".el-dialog").last
        dialog.wait_for(state="visible", timeout=5000)
        dialog.locator("input").first.fill("total")
        dialog.locator("textarea").fill("42")
        page.wait_for_timeout(300)
        dialog.get_by_role("button", name="保存").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "03_drawer_saved.png"))
        check("保存后表格出现新键", drawer.get_by_text("total").count() > 0)
        check("抽屉统计显示 1 个键", "1 个键" in drawer.inner_text())

        page.keyboard.press("Escape")
        page.wait_for_timeout(600)

        page.goto(BASE + "/visual-plugins", wait_until="networkidle")
        page.wait_for_selector(".plugin-link", timeout=15000)
        page.locator(".plugin-link").first.click()
        page.wait_for_selector(".node-card", timeout=15000)
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "04_editor.png"), full_page=True)

        nodes = page.locator(".node-card")
        check("编辑器渲染出 4 个节点", nodes.count() == 4)
        cards = [nodes.nth(i).inner_text() for i in range(nodes.count())]
        check("存储节点摘要显示「自增 · total」", any("自增" in c and "total" in c for c in cards))

        for i in range(nodes.count()):
            if "自增" in cards[i]:
                nodes.nth(i).click()
                break
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "05_storage_form.png"), full_page=True)
        body = page.inner_text("body")
        check("表单显示「数据键名」", "数据键名" in body)
        check("表单显示「每次增加」", "每次增加" in body)
        check("表单提示存储上限", "2 MB" in body)

        check("页面无 JS 报错", not [e for e in errors if "favicon" not in e.lower()])
        if errors:
            print("console errors:", errors[:5])

        browser.close()

    failed = [n for n, ok in results if not ok]
    print("\n" + "=" * 40)
    print(f"通过 {len(results) - len(failed)}/{len(results)}")
    print(f"截图目录：{OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
