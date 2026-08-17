"""可视化插件页面冒烟测试（Playwright）。

前置条件：测试服务运行在 127.0.0.1:9530，且已初始化 admin/admin123。
用法：.venv\\Scripts\\python.exe scripts\\visual_plugin_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:9530"
OUT = Path(__file__).resolve().parent.parent / "data" / "ui_visual"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    results: list[tuple[str, bool]] = []
    console_errors: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail and not cond else ""))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 940})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # 1. 登录
        page.goto(BASE + "/login", wait_until="networkidle")
        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click(".login-btn")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        check("登录进入仪表盘", "仪表盘" in page.content())
        try:
            page.wait_for_selector("text=发现新版本", timeout=8000)
            banner_ok = True
        except Exception:
            banner_ok = False
        check("更新横幅显示新版本", banner_ok)
        page.screenshot(path=str(OUT / "00_update_banner.png"))

        # 2. 侧边栏入口
        page.click("text=可视化插件编写")
        page.wait_for_selector("text=新建插件", timeout=8000)
        check("可视化插件列表页打开", "可视化插件编写" in page.content() and "新建插件" in page.content())
        page.screenshot(path=str(OUT / "01_list.png"), full_page=True)

        # 3. 新建插件
        page.click("text=新建插件")
        page.wait_for_selector(".el-dialog input", timeout=5000)
        plugin_name = f"冒烟流程{int(time.time())}"
        page.fill(".el-dialog input", plugin_name)
        page.click('button:has-text("创建并编辑")')
        page.wait_for_selector(".palette-item", timeout=10000)
        page.wait_for_timeout(500)
        check(
            "进入流程编辑器",
            page.locator(".palette-item").count() >= 10
            and "触发方式" in page.locator(".palette").inner_text(),
        )
        page.screenshot(path=str(OUT / "02_editor_empty.png"), full_page=True)

        # 4. 拖拽组件
        canvas = page.locator(".canvas")
        listener = page.locator(".palette-item", has_text="群聊监听").first
        try:
            listener.drag_to(canvas, target_position={"x": 300, "y": 120})
        except Exception:
            # 兜底：手动派发 HTML5 拖放事件
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('群聊监听'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'listener_group');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 300, clientY: rect.top + 120 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_selector(".node-card", timeout=5000)
        check("拖入群聊监听节点", page.locator(".node-card").count() >= 1)
        page.screenshot(path=str(OUT / "03_after_listener.png"))

        # 拖入条件判断（原与/或/非）
        logic_item = page.locator(".palette-item", has_text="条件判断").first
        try:
            logic_item.drag_to(canvas, target_position={"x": 300, "y": 240})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('条件判断'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'logic');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 300, clientY: rect.top + 240 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(600)
        check("拖入条件判断节点", page.locator(".node-card").count() >= 2)
        check("条件判断节点有双出口", page.locator(".port-out.true").count() >= 1 and page.locator(".port-out.false").count() >= 1)
        page.locator(".node-card").nth(1).click()
        page.wait_for_timeout(300)
        check("条件判断默认一行条件", page.locator(".cond-row").count() >= 1)

        # 拖入发送消息
        send_item = page.locator(".palette-item", has_text="发送消息").first
        try:
            send_item.drag_to(canvas, target_position={"x": 300, "y": 360})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('发送消息'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'send');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 300, clientY: rect.top + 360 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(600)
        check("拖入发送消息节点", page.locator(".node-card").count() >= 3)
        page.screenshot(path=str(OUT / "04_after_nodes.png"))

        # 5. 选中监听节点并配置关键词
        page.locator(".node-card").first.click()
        page.wait_for_timeout(400)
        check("配置面板显示监听类型", "监听类型" in page.content())
        kw = page.locator('.el-form-item:has-text("触发关键词") input')
        if kw.count():
            kw.fill("你好")
        at_me = page.locator('.el-form-item:has-text("仅当@我时触发") .el-switch')
        if at_me.count():
            at_me.click()
        check("群聊监听支持仅@我触发", at_me.count() >= 1)
        page.screenshot(path=str(OUT / "05_config.png"))

        # 5.1 变量栏与缩放工具
        check("底部显示可用变量胶囊", page.locator(".var-bar .var-pill").count() >= 5)
        # 滚轮缩放：向上滚动放大
        world_before_zoom = page.locator(".world").get_attribute("style")
        page.locator(".canvas").hover()
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(250)
        world_after_zoom = page.locator(".world").get_attribute("style")
        check("鼠标滚轮向上缩放放大", world_before_zoom != world_after_zoom)
        check("画布不再显示缩放滑块", page.locator(".zoom-slider").count() == 0)

        # 5.1.1 画布平移（在空白处拖拽）
        canvas_box = page.locator(".canvas").bounding_box()
        world_before = page.locator(".world").get_attribute("style")
        page.mouse.move(canvas_box["x"] + 60, canvas_box["y"] + 60)
        page.mouse.down()
        page.mouse.move(canvas_box["x"] + 170, canvas_box["y"] + 110, steps=12)
        page.mouse.up()
        page.wait_for_timeout(250)
        world_after = page.locator(".world").get_attribute("style")
        check("拖拽空白处平移画布", world_before != world_after)

        # 5.1.1b 负坐标区域（左/上）也可拖动画布，且画布为抓取光标
        cursor = page.evaluate("getComputedStyle(document.querySelector('.canvas')).cursor")
        check("画布抓取光标", cursor == "grab", cursor)
        pan_before2 = page.locator(".world").get_attribute("style")
        page.mouse.move(canvas_box["x"] + 30, canvas_box["y"] + 30)
        page.mouse.down()
        page.mouse.move(canvas_box["x"] + 100, canvas_box["y"] + 70, steps=10)
        page.mouse.up()
        page.wait_for_timeout(250)
        pan_after2 = page.locator(".world").get_attribute("style")
        check("负坐标区域可平移画布", pan_before2 != pan_after2)

        # 5.1.2 节点拖动
        card_before = page.locator(".node-card").first.bounding_box()
        if card_before:
            page.mouse.move(card_before["x"] + 120, card_before["y"] + 36)
            page.mouse.down()
            page.mouse.move(card_before["x"] + 220, card_before["y"] + 66, steps=12)
            page.mouse.up()
            page.wait_for_timeout(250)
            card_after = page.locator(".node-card").first.bounding_box()
            check(
                "拖动节点位置变化",
                card_after
                and (abs(card_after["x"] - card_before["x"]) > 5 or abs(card_after["y"] - card_before["y"]) > 5),
            )
        else:
            check("拖动节点位置变化", False, "节点定位失败")

        # 5.2 变量拖入发送消息输入框
        page.locator(".node-card").nth(2).click()
        page.wait_for_timeout(300)
        msg_input = page.locator(".msg-row .el-input input").first
        if msg_input.count():
            pill = page.locator(".var-pill", has_text="msg").first
            try:
                pill.drag_to(msg_input)
            except Exception:
                page.evaluate(
                    """() => {
                        const pill = [...document.querySelectorAll('.var-pill')].find(e => e.innerText.trim() === 'msg');
                        const input = document.querySelector('.msg-row .el-input input');
                        const dt = new DataTransfer();
                        dt.setData('text/visual-var', 'msg');
                        pill.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                        input.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                        input.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    }"""
                )
            page.mouse.up()
            page.wait_for_timeout(300)
            val = msg_input.input_value()
            check("变量拖入消息输入框", "{{msg}}" in val, val)
        else:
            check("变量拖入消息输入框", False, "未找到消息输入框")

        # 5.3 再拖一个发送消息，用端口拖拽连接 条件不成立 -> 新发送
        send_item2 = page.locator(".palette-item", has_text="发送消息").first
        try:
            send_item2.drag_to(canvas, target_position={"x": 620, "y": 360})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('发送消息'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'send');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 620, clientY: rect.top + 360 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        # 选中条件判断节点（第2个），从其“否”端口拖到第4个节点的输入端口
        page.locator(".node-card").nth(1).click()
        page.wait_for_timeout(200)
        src_box = page.locator(".node-card").nth(1).locator(".port-out.false").bounding_box()
        dst_box = page.locator(".node-card").nth(3).locator(".port-in").bounding_box()
        if src_box and dst_box:
            page.mouse.move(src_box["x"] + src_box["width"] / 2, src_box["y"] + src_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(dst_box["x"] + dst_box["width"] / 2, dst_box["y"] + dst_box["height"] / 2, steps=20)
            page.mouse.up()
            page.wait_for_timeout(400)
            check("端口拖拽创建连线", page.locator("svg .edge-line.false").count() >= 1)
        else:
            check("端口拖拽创建连线", False, "端口定位失败")
        page.screenshot(path=str(OUT / "05_ports.png"))

        # 5.4 定时任务多模式
        sched_item = page.locator(".palette-item", has_text="定时任务").first
        try:
            sched_item.drag_to(canvas, target_position={"x": 300, "y": 480})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('定时任务'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'schedule');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 300, clientY: rect.top + 480 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        sched = page.locator(".node-card", has_text="定时任务").first
        sched.click()
        page.wait_for_timeout(300)
        check("定时任务触发模式配置", "触发模式" in page.locator(".config-panel").inner_text())
        mode_select = page.locator('.el-form-item:has-text("触发模式") .el-select').first
        mode_select.click()
        page.wait_for_timeout(300)
        page.locator(".el-select-dropdown__item", has_text="每天定点触发").first.click()
        page.wait_for_timeout(300)
        check("每天定点模式显示时间选择", page.locator(".el-form-item", has_text="触发时间").count() >= 1)
        page.screenshot(path=str(OUT / "05_schedule.png"))

        # 5.5 WebHook 节点：请求体保存到自定义变量
        canvas_box2 = page.locator(".canvas").bounding_box()
        page.mouse.click(canvas_box2["x"] + 80, canvas_box2["y"] + 80)
        webhook_item = page.locator(".palette-item", has_text="WebHook").first
        try:
            webhook_item.drag_to(canvas, target_position={"x": 900, "y": 480})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('WebHook'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'listener_webhook');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 900, clientY: rect.top + 480 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        wh_path = page.locator('.el-form-item:has-text("WebHook 路径") input')
        if wh_path.count():
            wh_path.fill("/webhook/test")
        wh_var = page.locator('.el-form-item:has-text("保存到变量") input')
        if wh_var.count():
            wh_var.fill("hook_data")
        check("WebHook 节点可配置保存变量", wh_var.count() >= 1)
        page.screenshot(path=str(OUT / "05_webhook.png"))

        # 5.5b 变量区按触发分支显示：WebHook 分支不显示消息变量
        page.locator(".node-card", has_text="WebHook").first.click()
        page.wait_for_timeout(300)
        pills_wh = [p.strip() for p in page.locator(".var-bar .var-pill").all_inner_texts()]
        check(
            "WebHook 分支不显示消息变量",
            "sender.nickname" not in pills_wh and "msg" not in pills_wh,
            str(pills_wh),
        )
        # 消息分支显示 sender
        page.locator(".node-card", has_text="发送但继续").first.click()
        page.wait_for_timeout(300)
        pills_msg = [p.strip() for p in page.locator(".var-bar .var-pill").all_inner_texts()]
        check("消息分支显示 sender", "sender.nickname" in pills_msg, str(pills_msg))

        # 5.6 API请求节点
        api_item = page.locator(".palette-item", has_text="API请求").first
        try:
            api_item.drag_to(canvas, target_position={"x": 900, "y": 620})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('API请求'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'api');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 900, clientY: rect.top + 620 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        api_url = page.locator('.el-form-item:has-text("URL") input').first
        if api_url.count():
            api_url.fill("https://example.com/api")
        api_var = page.locator('.el-form-item:has-text("保存到变量") input').first
        if api_var.count():
            api_var.fill("api_resp")
        check("API请求节点可配置", api_url.count() >= 1)
        page.screenshot(path=str(OUT / "05_api.png"))

        # 5.7 循环遍历自动配对循环结束（左侧配对线、列表隐藏、同生共死）
        loop_item = page.locator(".palette-item", has_text="循环遍历").first
        try:
            loop_item.drag_to(canvas, target_position={"x": 300, "y": 700})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('循环遍历'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'loop');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 300, clientY: rect.top + 700 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        check("循环遍历自动创建循环结束", page.locator(".node-card", has_text="循环结束").count() >= 1)
        check("循环结束不在组件列表", page.locator(".palette-item", has_text="循环结束").count() == 0)
        check("配对左侧连线存在", page.locator("svg .pair-line").count() >= 1)

        # 5.8 会话入口自动配对会话结束
        entry_item = page.locator(".palette-item", has_text="会话入口").first
        try:
            entry_item.drag_to(canvas, target_position={"x": 620, "y": 700})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('会话入口'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'conversation_entry');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 620, clientY: rect.top + 700 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        check("会话入口自动创建会话结束", page.locator(".node-card", has_text="会话结束").count() >= 1)
        check("会话结束不在组件列表", page.locator(".palette-item", has_text="会话结束").count() == 0)
        check("配对连线共两条", page.locator("svg .pair-line").count() >= 2)
        check("功能大类存在", "功能" in page.locator(".palette").inner_text())
        page.screenshot(path=str(OUT / "05_pairs.png"))

        # 5.8b 选项交互：按选项数量分出输出端口
        choice_item = page.locator(".palette-item", has_text="选项交互").first
        try:
            choice_item.drag_to(canvas, target_position={"x": 900, "y": 800})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('选项交互'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'choice');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 900, clientY: rect.top + 800 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        check("选项交互节点可配置", page.locator('.el-form-item:has-text("提示文本")').count() >= 1)
        choice_ports = page.locator(".node-card").last.locator(".port-out").count()
        check("选项交互按选项分出输出端口", choice_ports >= 3, str(choice_ports))
        page.screenshot(path=str(OUT / "05_choice.png"))

        # 5.9 左上方向也可放置节点（世界坐标允许为负）
        cb3 = page.locator(".canvas").bounding_box()
        page.mouse.click(cb3["x"] + 40, cb3["y"] + 40)
        page.wait_for_timeout(200)
        listener2 = page.locator(".palette-item", has_text="群聊监听").first
        try:
            listener2.drag_to(canvas, target_position={"x": 40, "y": 40})
        except Exception:
            page.evaluate(
                """() => {
                    const item = [...document.querySelectorAll('.palette-item')].find(e => e.innerText.includes('群聊监听'));
                    const canvas = document.querySelector('.canvas');
                    const rect = canvas.getBoundingClientRect();
                    const dt = new DataTransfer();
                    dt.setData('text/visual-type', 'listener_group');
                    item.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
                    canvas.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                    canvas.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: rect.left + 40, clientY: rect.top + 40 }));
                }"""
            )
        page.mouse.up()
        page.wait_for_timeout(400)
        last_left = page.evaluate(
            """() => {
                const cards = document.querySelectorAll('.node-card');
                const el = cards[cards.length - 1];
                return parseFloat(el.style.left);
            }"""
        )
        check("左上方向可放置节点（负坐标）", last_left < 0, f"left={last_left}")

        # 6. 保存
        page.click('button:has-text("保存")')
        pid = page.url.rstrip("/").split("/").pop()
        saved_ok = False
        detail = ""
        for _ in range(30):
            page.wait_for_timeout(1000)
            try:
                api_count = page.evaluate(
                    """async (pid) => {
                        const r = await fetch('/api/visual-plugins/' + pid);
                        const data = await r.json();
                        return (data.flow?.nodes || []).length;
                    }""",
                    pid,
                )
            except Exception:
                api_count = -1
            canvas_count = page.locator(".node-card").count()
            if api_count == canvas_count:
                saved_ok = True
                break
        if not saved_ok:
            detail = f"30s 后 API节点数={api_count} 画布节点数={canvas_count}"
        check("保存流程", saved_ok, detail)

        # 7. “生成插件”已改为“更新插件”，不再展示代码
        check("编辑器不再显示生成插件按钮", page.locator('button:has-text("生成插件")').count() == 0)
        page.click('button:has-text("更新插件")')
        page.wait_for_timeout(800)
        check("未装配时提示先装配", "尚未装配" in page.content())

        # 7.1 注册临时机器人（已存在非空目录 -> 不重建脚手架）
        scratch = Path(r"E:\Web\nonebot-webui\data_smoke_tmp\smoke_bot")
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "README.md").write_text("smoke", encoding="utf-8")
        status = page.evaluate(
            """async (dir) => {
                const r = await fetch('/api/bots', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: 'smoke-bot', directory: dir, adapter: 'onebot_v11', host: '0.0.0.0', port: 18081, create_dir: true }),
                });
                return r.status;
            }""",
            str(scratch),
        )
        check("注册临时机器人", status in (200, 201), str(status))

        # 7.2 返回列表页，装配到机器人
        page.click('button:has-text("返回")')
        page.wait_for_selector("text=装配到机器人", timeout=8000)
        row = page.locator(".el-table__row", has_text=plugin_name).first
        row.locator('button:has-text("装配到机器人")').click()
        page.wait_for_selector(".el-dialog .el-select", timeout=5000)
        page.locator(".el-dialog .el-select").click()
        page.wait_for_selector(".el-select-dropdown__item", timeout=5000)
        page.locator(".el-select-dropdown__item", has_text="smoke-bot").first.click()
        page.click('.el-dialog button:has-text("安装")')
        page.wait_for_timeout(1200)
        check("列表页装配成功", "已安装" in page.content())
        page.screenshot(path=str(OUT / "06_installed.png"), full_page=True)

        # 7.3 验证落盘代码（编译式控制流，无流程 JSON 解释器）
        import glob

        files = glob.glob(str(scratch / "src" / "plugins" / "*.py"))
        check("生成的插件文件已写入机器人", len(files) >= 1, str(files))
        if files:
            content = Path(files[0]).read_text(encoding="utf-8")
            check("落盘代码为编译式控制流", "async def _step_" in content and "on_message" in content)
            check("落盘代码不内嵌流程 JSON 解释器", '"FLOW"' not in content and "run_flow" not in content)
            check("定时任务使用定点触发计算", "_seconds_until(9, 0)" in content)
            check("WebHook 请求体保存到变量", "ctx['hook_data'] = payload" in content)
            check("WebHook 载荷解析支持 JSON/表单/文本", "await request.json()" in content and "await request.form()" in content)
            check("API请求组件生成代码", "httpx.AsyncClient" in content and "ctx['api_resp']" in content)
            check("会话入口管理会话存储", 'ctx["session"] = _sess' in content and "_sessions.pop" in content)
            check("选项交互生成代码", "_choice_" in content and '"kind": "choice"' in content)
            check("群聊监听生成 @我 规则", "event.to_me" in content)

        # 7.4 重新进入编辑器，点“更新插件”自动重新装配
        page.locator(".el-table__row", has_text=plugin_name).first.locator('button:has-text("编辑")').click()
        page.wait_for_selector(".palette-item", timeout=8000)
        page.wait_for_timeout(500)
        page.click('button:has-text("更新插件")')
        page.wait_for_timeout(1500)
        check("更新插件自动重新装配", "已更新并重新装配" in page.content())
        check("编辑器不再展示代码弹窗", page.locator(".code-box").count() == 0)

        # 8. 创建机器人弹窗：目录输入框旁有“选择文件夹”按钮
        page.goto(BASE + "/bots", wait_until="domcontentloaded")
        page.wait_for_selector("text=创建机器人", timeout=8000)
        page.click("text=创建机器人")
        page.wait_for_selector(".dir-picker", timeout=5000)
        btn = page.locator('.dir-picker button:has-text("选择文件夹")')
        check("创建机器人弹窗含目录选择按钮", btn.count() >= 1)
        page.screenshot(path=str(OUT / "07_dir_picker.png"))
        page.keyboard.press("Escape")

        browser.close()

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
