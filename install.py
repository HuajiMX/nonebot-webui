"""NoneBot2 WebUI 一键安装脚本。

用法：
    python install.py                # 交互式安装（会询问管理员账号密码）
    python install.py --username admin --password 123456
    python install.py --skip-frontend   # 跳过前端构建
    python install.py --start          # 安装完成后启动服务
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
DATA_DIR = ROOT / "data"
CONFIG_FILE = DATA_DIR / "config.json"
USERS_FILE = DATA_DIR / "users.json"

# Windows 控制台中文显示
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def run(cmd: list[str], cwd: Path | None = None) -> int:
    print(">", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(cwd or ROOT))


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> Path:
    py = venv_python()
    if not py.exists():
        print("创建虚拟环境 .venv ...")
        if run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
            sys.exit("创建虚拟环境失败")
    print(f"虚拟环境：{VENV_DIR}")
    return py


def install_backend(py: Path) -> None:
    print("\n安装后端依赖 ...")
    req = ROOT / "requirements.txt"
    if run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req)]) != 0:
        sys.exit("后端依赖安装失败")


def npm_cmd() -> str:
    if os.name == "nt":
        return "npm.cmd"
    return "npm"


def build_frontend(force: bool = False) -> None:
    dist_index = ROOT / "frontend" / "dist" / "index.html"
    if dist_index.exists() and not force:
        print("检测到已构建的前端（frontend/dist），跳过前端构建。")
        print("如需重新构建：python install.py --force-build-frontend")
        return
    print("\n构建前端页面（需要 Node.js / npm）...")
    npm = npm_cmd()
    if run([npm, "--version"]) != 0:
        print("未检测到 npm，跳过前端构建。可安装 Node.js 后重新运行：python install.py")
        return
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").exists():
        if run([npm, "install", "--no-audit", "--no-fund"], cwd=frontend) != 0:
            sys.exit("前端依赖安装失败")
    if run([npm, "run", "build"], cwd=frontend) != 0:
        sys.exit("前端构建失败")
    print("前端构建完成")


def setup_admin(username: str, password: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    if USERS_FILE.exists():
        try:
            existing = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    if existing:
        print("已存在管理员账号，跳过初始化")
        return

    if not username:
        username = input("请输入管理员用户名 [admin]：").strip() or "admin"
    if not password:
        while True:
            p1 = getpass.getpass("请输入管理员密码（至少 6 位）：")
            if len(p1) < 6:
                print("密码过短，请重试")
                continue
            p2 = getpass.getpass("请再次输入密码：")
            if p1 != p2:
                print("两次输入不一致，请重试")
                continue
            password = p1
            break

    sys.path.insert(0, str(ROOT))
    from backend.security import create_user

    create_user(username, password)
    print(f"管理员账号「{username}」创建完成")


def write_config(host: str, port: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
    config["host"] = host
    config["port"] = port
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_start_scripts() -> None:
    if os.name == "nt":
        start_bat = ROOT / "启动WebUI.bat"
        start_bat.write_text(
            '@echo off\r\n'
            'cd /d "%~dp0"\r\n'
            '"%~dp0.venv\\Scripts\\python.exe" start.py\r\n'
            'pause\r\n',
            encoding="utf-8",
        )
        print(f"已生成启动脚本：{start_bat}")


def main() -> None:
    parser = argparse.ArgumentParser(description="NoneBot2 WebUI 一键安装")
    parser.add_argument("--username", default="", help="管理员用户名")
    parser.add_argument("--password", default="", help="管理员密码")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=9527, help="监听端口")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    parser.add_argument(
        "--force-build-frontend", action="store_true", help="强制重新构建前端"
    )
    parser.add_argument("--start", action="store_true", help="安装完成后启动服务")
    args = parser.parse_args()

    print("=" * 50)
    print("  NoneBot2 WebUI 一键安装")
    print("=" * 50)

    py = ensure_venv()
    # 依赖只装进 .venv；若 install.py 由系统 Python 运行，后续导入
    # pydantic 等第三方库会失败（ModuleNotFoundError）。检测到当前不在
    # 虚拟环境中时，自动切换到 .venv 的 Python 重新执行本脚本。
    if os.environ.get("NB_WEBUI_USE_VENV") != "1" and Path(sys.prefix).resolve() != VENV_DIR.resolve():
        print(f"切换到虚拟环境 Python：{py}")
        os.environ["NB_WEBUI_USE_VENV"] = "1"
        os.execv(str(py), [str(py), str(ROOT / "install.py"), *sys.argv[1:]])
    install_backend(py)
    if not args.skip_frontend:
        build_frontend(force=args.force_build_frontend)
    setup_admin(args.username, args.password)
    write_config(args.host, args.port)
    write_start_scripts()

    print("\n安装完成！")
    print(f"启动命令：{venv_python()} start.py")
    if os.name == "nt":
        print("或在 Windows 下双击「启动WebUI.bat」")
    if args.start:
        print("\n正在启动服务 ...")
        os.execv(str(py), [str(py), str(ROOT / "start.py")])


if __name__ == "__main__":
    main()
