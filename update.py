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
import re
import shutil
import signal
import socket
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
MAX_PACKAGE_BYTES = 512 * 1024 * 1024  # 发布包大小上限 512MB
# 本地生成物/用户数据，发布包一律不得包含，覆盖时也必须跳过
PROTECTED_ENTRIES = {"data", ".venv", "启动WebUI.bat"}


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
    # 枚举监听端口的进程（psutil 在部分 Linux 环境会因权限失败，失败不阻塞终止）
    try:
        import psutil

        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN" and conn.pid:
                    targets.add(conn.pid)
        except Exception as exc:  # noqa: BLE001
            log(f"psutil 无法枚举端口 {port} 的占用进程（{exc}）")
    except Exception as exc:  # noqa: BLE001
        log(f"psutil 不可用：{exc}")

    for pid_ in targets:
        try:
            import psutil

            psutil.Process(pid_).terminate()
            log(f"已请求停止进程 {pid_}")
        except Exception as exc:  # noqa: BLE001
            log(f"终止进程 {pid_} 失败（{exc}）")
            if os.name != "nt":
                try:
                    os.kill(pid_, signal.SIGTERM)
                    log(f"已向进程 {pid_} 发送 SIGTERM")
                except Exception as exc2:  # noqa: BLE001
                    log(f"向进程 {pid_} 发送 SIGTERM 失败：{exc2}")

    for _ in range(15):
        if not _port_alive(port):
            return
        time.sleep(1)
    log("等待端口释放超时，继续尝试更新")


def _port_alive(port: int) -> bool:
    # 优先用 TCP 直连探测，不依赖 psutil（避免权限问题导致误判）
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        pass
    try:
        import psutil

        return any(
            conn.laddr and conn.laddr.port == port and conn.status == "LISTEN"
            for conn in psutil.net_connections(kind="tcp")
        )
    except Exception:  # noqa: BLE001
        return False


def wait_server_up(port: int, timeout: float = 25) -> bool:
    """等待端口恢复监听，用于确认重启是否成功。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_alive(port):
            return True
        time.sleep(1)
    return False


def download(url: str, dest: Path) -> None:
    log(f"下载发布包：{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "nonebot-webui-updater"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
        total = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PACKAGE_BYTES:
                raise RuntimeError(
                    f"发布包超过大小上限（{MAX_PACKAGE_BYTES // (1024 * 1024)}MB），已中止"
                )
            fh.write(chunk)
    log(f"下载完成：{dest.stat().st_size} 字节")


def verify_checksum(url: str, path: Path) -> None:
    """尝试下载发布包同名的 .sha256 文件并校验；无 sidecar 时仅提示（兼容自定义源）。"""
    sidecar = url + ".sha256"
    try:
        req = urllib.request.Request(
            sidecar, headers={"User-Agent": "nonebot-webui-updater"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read(4096).decode("utf-8", errors="replace").strip()
    except Exception as exc:  # noqa: BLE001
        log(f"未找到校验文件 {sidecar}（{exc}），跳过校验")
        return
    expected = content.split()[0].strip().lower() if content else ""
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("校验文件格式无效，已中止更新")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"发布包 SHA-256 校验失败（期望 {expected}，实际 {actual}），已中止更新"
        )
    log("发布包 SHA-256 校验通过")


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

        # 防御性检查：发布包不得包含本地生成物/用户数据，否则拒绝更新
        protected_hit = [
            str(p) for p in tmp_path.iterdir() if p.name in PROTECTED_ENTRIES
        ]
        if protected_hit:
            raise RuntimeError(
                f"发布包包含受保护条目（{protected_hit}），已拒绝更新"
            )

        req_old = ROOT / "requirements.txt"
        req_new = tmp_path / "requirements.txt"
        old_hash = sha256(req_old) if req_old.exists() else ""
        new_hash = sha256(req_new) if req_new.exists() else ""

        # 覆盖代码（显式跳过受保护条目，双保险）
        for entry in tmp_path.iterdir():
            if entry.name in PROTECTED_ENTRIES:
                continue
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
    popen_kwargs = {}
    if os.name != "nt":
        # 让新服务脱离更新进程的会话，避免更新脚本退出时被连带结束
        popen_kwargs["start_new_session"] = True
    with open(log_file, "ab") as fh:
        subprocess.Popen(
            [str(python), str(ROOT / "start.py")],
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
            **popen_kwargs,
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

        # 先下载（此时旧服务仍在运行，前端可实时看到进度），再停服替换
        download(args.url, tmp_zip)
        verify_checksum(args.url, tmp_zip)
        stop_server(args.port, args.pid or None)
        time.sleep(2)

        apply_update(tmp_zip)
        log("更新内容应用完成")

        if not args.skip_restart:
            restart_server()
            if wait_server_up(args.port):
                log("===== 更新完成，服务已重启 =====")
            else:
                log("===== 更新完成，但未检测到服务启动，请手动重启 WebUI 服务 =====")
        else:
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
