"""启动 NoneBot2 WebUI 服务。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Windows 控制台中文显示
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

config_file = ROOT / "data" / "config.json"
host = "0.0.0.0"
port = 9527
if config_file.exists():
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
        host = config.get("host", host)
        port = int(config.get("port", port))
    except (json.JSONDecodeError, ValueError):
        pass

print(f"NoneBot2 WebUI 已启动：http://127.0.0.1:{port}")
print("按 Ctrl+C 停止服务")
uvicorn.run("backend.main:app", host=host, port=port, reload=False)
