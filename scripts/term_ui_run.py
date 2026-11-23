"""启动终端冒烟环境并跑浏览器测试。"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests

PORT = 9530
BASE = f"http://127.0.0.1:{PORT}"


def main():
    data_dir = tempfile.mkdtemp(prefix="nb_term_ui_")
    bot_dir = os.path.join(data_dir, "botdir")
    os.makedirs(bot_dir)
    with open(os.path.join(bot_dir, "marker.txt"), "w", encoding="utf-8") as f:
        f.write("x")

    env = os.environ.copy()
    env["NB_WEBUI_DATA"] = data_dir
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=r"E:\Web\nonebot-webui",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            try:
                if requests.get(BASE + "/api/health", timeout=1).ok:
                    break
            except Exception:
                time.sleep(0.5)
        s = requests.Session()
        s.post(BASE + "/api/auth/setup", json={"username": "admin", "password": "admin123"}, timeout=5)
        # 注册用户真实机器人目录（已存在且非空 -> managed=False，不影响真实数据，只测终端）
        r = s.post(
            BASE + "/api/bots",
            json={"name": "TestBot", "directory": r"E:\Bot\TestBot", "create_dir": False},
            timeout=30,
        )
        bot_id = r.json()["id"]
        print("bot_id:", bot_id)
        rc = subprocess.call([sys.executable, r"scripts\term_browser_smoke.py", bot_id], cwd=r"E:\Web\nonebot-webui")
        print("smoke rc:", rc)
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
