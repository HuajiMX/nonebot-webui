#!/usr/bin/env bash
# NoneBot2 WebUI 一键安装脚本（Linux / macOS）
#
# 一行命令安装（需先安装 Python 3.10+）：
#   curl -fsSL https://raw.githubusercontent.com/HuajiMX/nonebot-webui/main/install.sh | bash -s HuajiMX/nonebot-webui
#
# 本机运行：bash install.sh owner/repo
# 也可用环境变量：REPO=owner/repo URL=... USERNAME=... PASSWORD=... bash install.sh

set -euo pipefail

REPO="${1:-${REPO:-}}"
URL="${2:-${URL:-}}"
USERNAME="${USERNAME:-}"
PASSWORD="${PASSWORD:-}"
INSTALL_DIR="${INSTALL_DIR:-$(pwd)/nonebot-webui}"

echo "===== NoneBot2 WebUI 一键安装 ====="

# 1. 检查 Python
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "[错误] 未检测到 Python，请先安装 Python 3.10+"
    exit 1
fi

# 2. 确定下载地址
if [ -z "$URL" ]; then
    if [ -n "$REPO" ]; then
        URL="https://github.com/${REPO}/releases/latest/download/nonebot-webui.zip"
    else
        echo "[错误] 请传入 owner/repo（bash install.sh owner/repo）或设置 URL 环境变量"
        exit 1
    fi
fi

# 3. 下载发布包
TMP_ZIP="$(mktemp -t nonebot-webui.XXXXXX.zip)"
echo "下载发布包：$URL"
curl -fsSL "$URL" -o "$TMP_ZIP"

# 4. 解压到安装目录
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
echo "解压到：$INSTALL_DIR"
unzip -q -o "$TMP_ZIP" -d "$INSTALL_DIR"
rm -f "$TMP_ZIP"

# 5. 运行安装脚本（已内置前端，自动跳过 npm 构建）
cd "$INSTALL_DIR"
if [ -n "$USERNAME" ] && [ -n "$PASSWORD" ]; then
    python3 install.py --username "$USERNAME" --password "$PASSWORD"
else
    python3 install.py
fi

echo ""
echo "===== 安装完成 ====="
echo "项目位置：$INSTALL_DIR"
echo "启动方式：cd \"$INSTALL_DIR\" 然后 ./.venv/bin/python start.py"
