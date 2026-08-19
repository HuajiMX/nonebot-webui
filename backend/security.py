"""密码哈希与会话工具。"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from . import config
from .models import User
from .storage import load_json, save_json


_session_lock = threading.Lock()
# token -> {username, expires_at}
_sessions: Dict[str, dict] = {}

_login_lock = threading.Lock()
# key -> [失败时间戳]，用于登录/初始化限流
_login_failures: Dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW = 15 * 60

_setup_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """返回 (hash, salt)，使用 PBKDF2-HMAC-SHA256。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)


def get_users() -> dict[str, User]:
    raw = load_json(config.USERS_FILE, {}) or {}
    return {name: User(**data) for name, data in raw.items()}


def save_users(users: dict[str, User]) -> None:
    save_json(
        config.USERS_FILE,
        {name: user.model_dump() for name, user in users.items()},
    )


def create_user(username: str, password: str) -> User:
    users = get_users()
    if username in users:
        raise ValueError("用户名已存在")
    password_hash, salt = hash_password(password)
    user = User(username=username, password_hash=password_hash, salt=salt, created_at=_now(), updated_at=_now())
    users[username] = user
    save_users(users)
    return user


def authenticate(username: str, password: str) -> Optional[User]:
    user = get_users().get(username)
    if user and verify_password(password, user.password_hash, user.salt):
        return user
    return None


def change_password(username: str, old_password: str, new_password: str) -> None:
    users = get_users()
    user = users.get(username)
    if not user or not verify_password(old_password, user.password_hash, user.salt):
        raise ValueError("原密码不正确")
    password_hash, salt = hash_password(new_password)
    user.password_hash = password_hash
    user.salt = salt
    user.updated_at = _now()
    users[username] = user
    save_users(users)
    # 使该用户旧会话失效
    with _session_lock:
        for token in list(_sessions):
            if _sessions[token]["username"] == username:
                _sessions.pop(token, None)


def create_session(username: str, ttl: int = 7 * 24 * 3600) -> str:
    token = secrets.token_urlsafe(32)
    with _session_lock:
        _sessions[token] = {"username": username, "expires_at": time.time() + ttl}
    return token


def validate_session(token: str) -> Optional[str]:
    if not token:
        return None
    with _session_lock:
        sess = _sessions.get(token)
        if not sess:
            return None
        if sess["expires_at"] < time.time():
            _sessions.pop(token, None)
            return None
        return sess["username"]


def destroy_session(token: str) -> None:
    with _session_lock:
        _sessions.pop(token, None)


def destroy_user_sessions(username: str) -> None:
    with _session_lock:
        for token in list(_sessions):
            if _sessions[token]["username"] == username:
                _sessions.pop(token, None)


def has_users() -> bool:
    return bool(get_users())


def setup_initial_user(username: str, password: str) -> User:
    """首次初始化管理员（原子操作），并发请求时仅第一个成功。"""
    with _setup_lock:
        if get_users():
            raise ValueError("系统已初始化，不能重复设置")
        return create_user(username, password)


def _prune_login_failures(key: str) -> None:
    now = time.time()
    _login_failures[key] = [
        t for t in _login_failures.get(key, []) if now - t < _LOGIN_WINDOW
    ]


def is_login_blocked(key: str) -> bool:
    """滑动窗口内失败次数达到上限则返回 True。"""
    with _login_lock:
        _prune_login_failures(key)
        return len(_login_failures.get(key, ())) >= _LOGIN_MAX_ATTEMPTS


def record_login_failure(key: str) -> None:
    with _login_lock:
        _prune_login_failures(key)
        _login_failures.setdefault(key, []).append(time.time())


def clear_login_failures(key: str) -> None:
    with _login_lock:
        _login_failures.pop(key, None)
