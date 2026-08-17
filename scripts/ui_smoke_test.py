"""NoneBot2 WebUI 前端冒烟测试（Playwright）。

前置条件：服务已运行在 127.0.0.1:9527，且存在管理员账号 admin/admin123
以及一个测试机器人（如 demo-bot）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:9527"
OUT = Path(__file__).resolve().parent.parent / "data" / "ui"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    results: list[tuple[str, bool]] = []
    console_errors: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail and not cond else ""))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # 1. 登录页
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(1200)
        check(
            "打开登录页",
            "登录" in page.content() or "/login" in page.url,
            page.url,
        )
        page.screenshot(path=str(OUT / "01_login.png"))

        # 主题色检查
        primary = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--el-color-primary').trim()"
        )
        check("主题色为 #ea5252", primary.lower() == "#ea5252", primary)

        # 2. 登录
        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click('button:has-text("登")')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)
        check("登录后进入仪表盘", "仪表盘" in page.content() and "CPU 占用" in page.content())
        brand_bg = page.evaluate(
            "getComputedStyle(document.querySelector('.brand-logo')).backgroundColor"
        )
        check("品牌 Logo 使用主题色", brand_bg == "rgb(234, 82, 82)", brand_bg)
        page.screenshot(path=str(OUT / "02_dashboard.png"), full_page=True)

        # 3. 机器人列表
        page.click("text=机器人管理")
        page.wait_for_selector(".el-table__row", timeout=10000)
        page.wait_for_timeout(500)
        check("机器人列表包含 demo-bot", "demo-bot" in page.content())
        page.screenshot(path=str(OUT / "03_bots.png"), full_page=True)

        # 4. 机器人详情 - 概览
        page.click("text=demo-bot")
        page.wait_for_timeout(1500)
        check("详情页概览加载", "基本信息" in page.content() and "编辑信息" in page.content())
        page.screenshot(path=str(OUT / "04_overview.png"), full_page=True)

        # 5. 日志
        page.click("text=运行日志")
        page.wait_for_timeout(3000)
        check("日志面板显示 NoneBot 日志", "NoneBot" in page.content())
        page.screenshot(path=str(OUT / "05_logs.png"))

        # 6. 插件
        page.click("text=插件管理")
        page.wait_for_selector(".el-table__row", timeout=10000)
        page.wait_for_timeout(500)
        content = page.content()
        check("插件列表显示 weather", "weather" in content)
        check("插件列表显示 hello_plugin", "hello_plugin" in content)
        page.screenshot(path=str(OUT / "06_plugins.png"), full_page=True)

        # 7. 终端
        page.click("text=终端")
        page.wait_for_timeout(3000)
        page.locator(".term-box").click(position={"x": 300, "y": 150})
        page.wait_for_timeout(500)
        page.keyboard.type("echo UI_TERM_OK\r")
        page.wait_for_timeout(4000)
        term_ok = page.evaluate(
            "!!document.querySelector('.xterm-rows') && document.querySelector('.xterm-rows').innerText.includes('UI_TERM_OK')"
        )
        check("终端 echo 输出正常", term_ok)
        page.screenshot(path=str(OUT / "07_terminal.png"))

        # 8. 设置
        page.click("text=系统设置")
        page.wait_for_selector("text=修改密码", timeout=8000)
        check("设置页加载", "修改密码" in page.content())
        page.screenshot(path=str(OUT / "08_settings.png"), full_page=True)

        browser.close()

    # 汇总
    failed = [n for n, ok in results if not ok]
    print("\n" + "=" * 40)
    print(f"通过 {len(results) - len(failed)}/{len(results)}")
    if console_errors:
        print("浏览器控制台错误：")
        for e in console_errors[:10]:
            print("  ", e[:300])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
