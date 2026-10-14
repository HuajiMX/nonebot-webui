"""NoneBot2 WebUI 一键更新脚本。

由 WebUI 的「更新」按钮触发：下载新版发布包 -> 停止服务 -> 备份 data/ ->
替换代码（保留 data/ 与 .venv）-> 依赖变化则重装 -> 重启服务。

托管方式自适应：
  * 服务由 systemd 单元托管时，先把自身搬进独立瞬时单元（systemd-run）脱离
    服务 cgroup，再用 systemctl stop/start 停启服务；
  * 其他方式（nohup / tmux / 启动WebUI.bat 等）沿用「直接终止进程 + 自行拉起」。

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


# ---------- systemd 托管感知 ----------
# 背景：若服务由 systemd 单元托管，本脚本作为它的子进程也位于同一个 cgroup。
# 一旦（为了替换代码而）杀掉服务主进程，systemd 会按 KillMode=control-group
# 清空该 cgroup，把本脚本一并终止 —— 而这一步发生在 apply_update() 之前，
# 结果是「更新看似执行、代码其实没换」。与此同时，单元上的 Restart=always
# 会在几秒后自动拉起服务，与本脚本自己 Popen 的实例抢同一个端口。
# 因此检测到 systemd 托管时：
#   ① 先用 systemd-run 把本脚本搬进独立瞬时单元，脱离服务 cgroup；
#   ② 用 systemctl stop/start 停启服务，交给 systemd 管理生命周期。
# 非 systemd 环境（nohup / tmux / 启动WebUI.bat 等）行为与此前完全一致。
DETACHED_ENV = "NB_WEBUI_UPDATE_DETACHED"
UNIT_ENV = "NB_WEBUI_UPDATE_UNIT"
DETACH_UNIT_PREFIX = "nbwebui-update"


def _cgroup_path(pid: int) -> str:
    """读取进程所属 cgroup（cgroup v2 形如 0::/system.slice/xxx.service）。"""
    try:
        text = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in reversed(text.strip().splitlines()):
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[2].strip():
            return parts[2].strip()
    return ""


def detect_service_unit(pid: int | None = None) -> str | None:
    """目标进程若由 systemd 服务单元托管，返回其单元名；否则返回 None。"""
    if os.name == "nt" or not Path("/run/systemd/system").exists():
        return None
    path = _cgroup_path(pid or os.getpid())
    if not path:
        return None
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return name if name.endswith(".service") else None


def _systemctl(action: str, unit: str, timeout: float = 90.0) -> bool:
    """按「用户级 → 系统级 → 免密 sudo」顺序尝试停/启单元，任一成功即返回 True。

    服务可能以普通用户身份运行，此时 `systemctl stop <系统单元>` 会被 polkit 拒绝，
    因此需要依次降级尝试（本项目的部署即依赖 `sudo -n`）；全部失败由调用方决定怎么办。
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    user_env = dict(os.environ)
    user_env["XDG_RUNTIME_DIR"] = runtime_dir
    user_env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")

    candidates = [
        ("systemctl --user", ["systemctl", "--user", action, unit], user_env),  # 用户级单元
        ("systemctl", ["systemctl", action, unit], None),  # 系统级（本身是 root 时可行）
    ]
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        candidates.append(
            ("sudo -n systemctl", ["sudo", "-n", "systemctl", action, unit], None)
        )

    reasons = []
    for label, cmd, env in candidates:
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, env=env
            )
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"{label}：{exc}")
            continue
        if proc.returncode == 0:
            log(f"systemctl {action} {unit} 成功（{label}）")
            return True
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        reasons.append(f"{label}：{detail[-1] if detail else proc.returncode}")
    log(f"systemctl {action} {unit} 全部失败：" + "；".join(reasons))
    return False


def _detach_candidates(unit: str) -> list:
    """构造「把自身搬离服务 cgroup」的候选命令：(说明, 命令, 环境)，按优先级排列。"""
    inner = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--systemd-unit", unit]
    unit_name = f"{DETACH_UNIT_PREFIX}-{int(time.time())}-{os.getpid()}"
    common = [
        "--collect",
        f"--unit={unit_name}",
        f"--setenv={DETACHED_ENV}=1",
        f"--setenv={UNIT_ENV}={unit}",
        f"--working-directory={ROOT}",
    ]
    user = group = None
    try:
        import grp
        import pwd

        user = pwd.getpwuid(os.getuid()).pw_name
        group = grp.getgrgid(os.getgid()).gr_name
    except Exception:  # noqa: BLE001
        pass
    root_common = list(common)
    if user:
        # 借 sudo 起系统级瞬时单元时，显式指定用户，避免把项目文件写成 root 属主
        root_common += [f"--property=User={user}", f"--property=Group={group or user}"]

    # ① 用户级管理器：同用户、无需提权（需 linger 或存在登录会话）
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    user_env = dict(os.environ)
    user_env["XDG_RUNTIME_DIR"] = runtime_dir
    user_env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")
    return [
        ("systemd-run --user", ["systemd-run", "--user", *common, *inner], user_env),
        ("sudo -n systemd-run", ["sudo", "-n", "systemd-run", *root_common, *inner], None),
        ("systemd-run（当前已是 root）", ["systemd-run", *root_common, *inner], None),
    ]


def detach_from_service_cgroup(unit: str) -> bool:
    """把本脚本搬进独立瞬时单元运行；成功返回 True（调用方应立即退出）。"""
    reasons = []
    for label, cmd, env in _detach_candidates(unit):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"{label}：{exc}")
            continue
        if proc.returncode == 0:
            log(f"已通过「{label}」把更新进程转入独立单元")
            return True
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        reasons.append(f"{label}：{detail[-1] if detail else proc.returncode}")
    log("搬离 cgroup 的候选方式均未成功：" + "；".join(reasons))
    return False


def _wait_port_released(port: int, timeout: int = 15) -> bool:
    for _ in range(timeout):
        if not _port_alive(port):
            return True
        time.sleep(1)
    return False


def stop_server(port: int, pid: int | None, unit: str = "") -> None:
    if unit:
        log(f"服务由 systemd 单元 {unit} 托管：改用 systemctl 停服")
        if _systemctl("stop", unit):
            if not _wait_port_released(port):
                log("systemctl stop 后端口仍未释放，继续更新流程")
            return
        # 停服失败时不能改用「直接杀进程」：那会触发 systemd 的 Restart=always
        # 在替换代码途中把服务拉起来，造成新旧代码互相踩踏。仅当端口本来就空着
        #（服务未在运行）才继续，否则中止并给出人工步骤。
        if not _port_alive(port):
            log("端口已释放（服务本就未运行），继续更新流程")
            return
        raise RuntimeError(
            f"无法停止 systemd 单元 {unit}（权限不足）。请手动执行："
            f"sudo systemctl stop {unit} → 覆盖代码 → sudo systemctl start {unit}"
        )

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


def restart_server(unit: str = "") -> None:
    if unit:
        log(f"服务由 systemd 单元 {unit} 托管：改用 systemctl 启动服务")
        if _systemctl("start", unit):
            return
        log(f"⚠️ 未能自动启动 systemd 单元 {unit}，请手动执行：sudo systemctl start {unit}")
        return

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


def _next_backup_dir() -> Path:
    """本次更新要用的数据备份目录。

    目录名只精确到秒，而「失败后立刻重试」「同一秒内被触发两次」都可能撞名，
    `shutil.copytree` 会直接抛 FileExistsError 把整个更新中断，故自动加序号避让。
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = ROOT.parent / f"data_backup_{stamp}"
    seq = 1
    while backup.exists():
        seq += 1
        backup = ROOT.parent / f"data_backup_{stamp}_{seq}"
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description="NoneBot2 WebUI 一键更新")
    parser.add_argument("--url", required=True, help="新版发布包 zip 地址")
    parser.add_argument("--port", type=int, default=9527, help="服务监听端口")
    parser.add_argument("--pid", type=int, default=0, help="服务进程 PID")
    parser.add_argument("--skip-restart", action="store_true", help="更新后不重启（测试用）")
    parser.add_argument("--systemd-unit", default="", help="服务所在的 systemd 单元（内部使用）")
    args = parser.parse_args()

    # 0) systemd 托管时，先把自己搬离服务 cgroup，否则会被 systemd 连带终止
    unit = args.systemd_unit.strip() or os.environ.get(UNIT_ENV, "").strip()
    if not unit:
        unit = detect_service_unit(args.pid or None) or ""
    if unit and os.environ.get(DETACHED_ENV) != "1":
        log(f"检测到服务由 systemd 单元 {unit} 托管，正在把更新进程搬离其 cgroup …")
        if detach_from_service_cgroup(unit):
            log("更新进程已转入独立单元继续执行，本进程退出")
            return 0
        log(
            "⚠️ 更新已中止：无法把更新进程搬离 systemd cgroup。继续执行的话，"
            "停止服务时本脚本会被 systemd 一并终止，可能造成代码只替换一半。"
            f"请手动更新：sudo systemctl stop {unit} → 覆盖代码 → sudo systemctl start {unit}"
        )
        return 1

    log("===== 更新开始 =====")
    tmp_zip = Path(tempfile.gettempdir()) / "nonebot-webui_update.zip"
    try:
        # 备份数据
        if DATA_DIR.exists():
            backup = _next_backup_dir()
            shutil.copytree(DATA_DIR, backup)
            log(f"已备份数据到：{backup}")
        else:
            log("未发现 data/，跳过备份")

        # 先下载（此时旧服务仍在运行，前端可实时看到进度），再停服替换
        download(args.url, tmp_zip)
        verify_checksum(args.url, tmp_zip)
        stop_server(args.port, args.pid or None, unit)
        time.sleep(2)

        apply_update(tmp_zip)
        log("更新内容应用完成")

        if not args.skip_restart:
            restart_server(unit)
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
