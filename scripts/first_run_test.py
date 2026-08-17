"""全新安装首次运行流程验证：/setup 初始化 → 登录 → 仪表盘。"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto("http://127.0.0.1:9527/", wait_until="networkidle")
        page.wait_for_timeout(1500)
        step1 = "/setup" in page.url or "初始化系统" in page.content()
        print(f"[{'PASS' if step1 else 'FAIL'}] 首次访问跳转初始化页: {page.url}")
        ok = ok and step1

        page.fill('input[placeholder="管理员用户名"]', "admin")
        page.fill('input[placeholder="密码（至少 6 位）"]', "admin123")
        page.fill('input[placeholder="确认密码"]', "admin123")
        page.click("button:has-text('完成初始化')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)
        step2 = "仪表盘" in page.content() and "CPU 占用" in page.content()
        print(f"[{'PASS' if step2 else 'FAIL'}] 初始化后自动登录进入仪表盘")
        ok = ok and step2

        page.goto("http://127.0.0.1:9527/", wait_until="networkidle")
        page.wait_for_timeout(1200)
        step3 = "仪表盘" in page.content()
        print(f"[{'PASS' if step3 else 'FAIL'}] 会话保持（刷新无需重新登录）")
        ok = ok and step3

        browser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
