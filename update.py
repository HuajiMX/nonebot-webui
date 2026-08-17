"""NoneBot2 WebUI 一键更新脚本。

由 WebUI 的「更新」按钮触发：下载新版发布包 -> 停止服务 -> 备份 data/ ->
替换代码（保留 data/ 与 .venv）-> 依赖变化则重装 -> 重启服务。

用法：
    python update.py --url <发布包zip地址> [--port 9527] [--pid <进程id>] [--skip-restart]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LOG_FILE = DATA_DIR / "update.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def stop_server(port: int, pid: int | None) -> None:
    targets = set()
    if pid:
        targets.add(pid)
    try:
        import psutil

        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
                targets.add(conn.pid)
        for pid_ in targets:
            try:
                psutil.Process(pid_).terminate()
                log(f"已请求停止进程 {pid_}")
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        log("无法通过 psutil 停止进程（将直接继续更新）")
    for _ in range(15):
        if not _port_alive(port):
            return
        time.sleep(1)
    log("等待端口释放超时，继续尝试更新")


def _port_alive(port: int) -> bool:
    try:
        import psutil

        return any(
            conn.laddr and conn.laddr.port == port and conn.status == "LISTEN"
            for conn in psutil.net_connections(kind="tcp")
        )
    except Exception:  # noqa: BLE001
        return False


def download(url: str, dest: Path) -> None:
    log(f"下载发布包：{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "nonebot-webui-updater"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    log(f"下载完成：{dest.stat().st_size} 字节")


def extract(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise RuntimeError(f"发布包包含非法路径：{member.filename}")
        zf.extractall(dest)


def verify_package(root: Path) -> None:
    required = [
        root / "install.py",
        root / "start.py",
        root / "backend" / "main.py",
        root / "frontend" / "dist" / "index.html",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"发布包缺少必要文件：{missing}")


def apply_update(zip_path: Path) -> None:
    """校验后把新代码覆盖到项目目录，保留 data/ 与 .venv。"""
    with tempfile.TemporaryDirectory(prefix="nbwebui_update_") as tmp:
        tmp_path = Path(tmp)
        extract(zip_path, tmp_path)
        verify_package(tmp_path)

        req_old = ROOT / "requirements.txt"
        req_new = tmp_path / "requirements.txt"
        old_hash = sha256(req_old) if req_old.exists() else ""
        new_hash = sha256(req_new) if req_new.exists() else ""

        # 覆盖代码（data/ 与 .venv 不在发布包内，天然保留）
        for entry in tmp_path.iterdir():
            target = ROOT / entry.name
            if entry.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(entry, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, target)
        log("新代码已就位")

        if new_hash and new_hash != old_hash:
            log("检测到依赖变化，重新安装依赖 ...")
            python = _venv_python()
            code = subprocess.call(
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")],
                cwd=str(ROOT),
            )
            if code != 0:
                raise RuntimeError(f"依赖安装失败（退出码 {code}）")
        else:
            log("依赖无变化，跳过安装")


def _venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def restart_server() -> None:
    python = _venv_python()
    if not python.exists():
        log("未找到 .venv，跳过自动重启（可手动运行 start.py）")
        return
    log("重启服务 ...")
    log_file = DATA_DIR / "webui_server.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0x08000000 if os.name == "nt" else 0
    with open(log_file, "ab") as fh:
        subprocess.Popen(
            [str(python), str(ROOT / "start.py")],
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="NoneBot2 WebUI 一键更新")
    parser.add_argument("--url", required=True, help="新版发布包 zip 地址")
    parser.add_argument("--port", type=int, default=9527, help="服务监听端口")
    parser.add_argument("--pid", type=int, default=0, help="服务进程 PID")
    parser.add_argument("--skip-restart", action="store_true", help="更新后不重启（测试用）")
    args = parser.parse_args()

    log("===== 更新开始 =====")
    tmp_zip = Path(tempfile.gettempdir()) / "nonebot-webui_update.zip"
    try:
        # 备份数据
        if DATA_DIR.exists():
            backup = ROOT.parent / f"data_backup_{time.strftime('%Y%m%d_%H%M%S')}"
            shutil.copytree(DATA_DIR, backup)
            log(f"已备份数据到：{backup}")
        else:
            log("未发现 data/，跳过备份")

        stop_server(args.port, args.pid or None)
        time.sleep(2)

        download(args.url, tmp_zip)
        apply_update(tmp_zip)
        log("更新内容应用完成")

        if not args.skip_restart:
            restart_server()
        log("===== 更新完成 =====")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"更新失败：{exc}")
        log("可通过备份目录恢复数据（data_backup_*）。")
        return 1
    finally:
        try:
            tmp_zip.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
