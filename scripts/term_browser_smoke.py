"""终端页面浏览器级冒烟测试（Playwright）：系统终端 + 机器人终端。

前置条件：服务运行在 127.0.0.1:9530，admin/admin123，且已有一个机器人。
用法：.venv\\Scripts\\python.exe scripts\\term_browser_smoke.py <bot_id>
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:9530"
OUT = Path(__file__).resolve().parent.parent / "data" / "ui_term"
OUT.mkdir(parents=True, exist_ok=True)


def wait_prompt(page, seconds=20):
    t0 = time.time()
    while time.time() - t0 < seconds:
        body = page.inner_text(".term-box")
        if ">" in body or "$" in body or "#" in body:
            return time.time() - t0
        # 启动失败时提前退出
        if "启动失败" in body or "终端错误" in body:
            return None
        page.wait_for_timeout(300)
    return None


def run_term(page, name, cmd, shot):
    took = wait_prompt(page)
    print(f"[{name}] prompt after: {took}s")
    body = page.inner_text(".term-box")
    print(f"[{name}] content head: {body.strip()[:150]!r}")
    page.keyboard.type(f"echo {cmd}")
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)
    body = page.inner_text(".term-box")
    ok = cmd in body
    print(f"[{name}] echo visible: {ok}")
    page.screenshot(path=str(OUT / shot))
    return ok


def main() -> int:
    bot_id = sys.argv[1]
    errors = []
    ws_events = []
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 940})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        def on_websocket(ws):
            ws_events.append("OPEN " + ws.url)
            def on_recv(d):
                ws_events.append(f"RECV {time.time() - t_start:6.1f}s {str(d)[:100]}")
            ws.on("framereceived", on_recv)
            ws.on("close", lambda: ws_events.append(f"CLOSED {ws.url}"))

        t_start = time.time()
        page.on("websocket", on_websocket)

        # 登录
        page.goto(BASE + "/login", wait_until="networkidle")
        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click(".login-btn")
        page.wait_for_timeout(1500)

        # 侧边栏终端入口 -> 系统终端
        has_nav = page.locator(".nav-item", has_text="终端").count() > 0
        print("sidebar terminal entry:", has_nav)
        results.append(("侧边栏终端入口", has_nav))
        page.click(".nav-item:has-text('终端')")
        page.wait_for_timeout(2500)
        print("url after nav:", page.url)
        page.screenshot(path=str(OUT / "00_nav.png"))
        page.wait_for_selector(".term-box .xterm", timeout=8000)
        page.wait_for_timeout(1500)
        results.append(("系统终端", run_term(page, "system", "SYS_OK", "10_system.png")))

        # 机器人详情 -> 终端标签
        page.goto(f"{BASE}/bots/{bot_id}", wait_until="networkidle")
        page.wait_for_selector(".layout", timeout=8000)
        # 确认旧的三个子标签已删除
        tabs_left = page.locator(".term-tabs").count() == 0
        print("protocol/custom tabs removed:", tabs_left)
        results.append(("协议端/自定义终端已删除", tabs_left))
        page.click('.el-tabs__item:has-text("终端")')
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "12_bot_tab.png"))
        page.wait_for_selector(".term-box .xterm", timeout=8000)
        page.wait_for_timeout(1500)
        results.append(("机器人环境终端", run_term(page, "bot", "BOT_OK", "11_bot.png")))

        browser.close()

    print("==== summary ====")
    all_ok = True
    for name, ok in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and bool(ok)
    if errors:
        print("console errors:", errors[:10])
    for e in ws_events:
        if e.startswith("OPEN") or "CLOSED" in e or "ready" in e:
            print(e)
    # 失败时输出全部帧，方便定位
    if not all_ok:
        print("---- all frames (bot session) ----")
        for e in ws_events:
            print(e)
    return 0 if all_ok else 1


if __name__ == "__main__":
    main()
