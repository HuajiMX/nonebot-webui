"""全局配置与路径管理。"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 数据目录，可通过环境变量覆盖（例如部署到其他位置时）
DATA_DIR = Path(os.environ.get("NB_WEBUI_DATA", str(PROJECT_ROOT / "data"))).resolve()

# 前端构建产物目录
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

# 默认数据文件
USERS_FILE = DATA_DIR / "users.json"
BOTS_FILE = DATA_DIR / "bots.json"
CONFIG_FILE = DATA_DIR / "config.json"

# 创建机器人时的默认配置
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_PLUGIN_DIR = "src/plugins"


def ensure_data_dir() -> None:
    """确保数据目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
