"""认证相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from .. import config
from ..deps import TOKEN_COOKIE, current_user
from ..models import ChangePasswordRequest, LoginRequest, SetupRequest
from ..security import (
    authenticate,
    change_password,
    clear_login_failures,
    create_session,
    destroy_session,
    has_users,
    is_login_blocked,
    record_login_failure,
    setup_initial_user,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _cookie_secure_flag() -> bool:
    """是否给会话 Cookie 加 Secure 标记（data/config.json 的 cookie_secure，默认关）。"""
    return bool(config.get_config().get("cookie_secure", False))


@router.get("/status")
def auth_status() -> dict:
    """是否已初始化（无用户时前端展示首次设置页）。"""
    return {"initialized": has_users()}


@router.post("/setup")
def setup(data: SetupRequest, request: Request) -> dict:
    if has_users():
        raise HTTPException(status_code=400, detail="系统已初始化，不能重复设置")
    ip = request.client.host if request.client else ""
    if is_login_blocked(f"setup:{ip}"):
        raise HTTPException(
            status_code=429,
            detail="尝试次数过多，请 15 分钟后再试",
            headers={"Retry-After": "900"},
        )
    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    try:
        setup_initial_user(username, data.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = create_session(username)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        secure=_cookie_secure_flag(),
    )
    return resp


@router.post("/login")
def login(data: LoginRequest, request: Request, response: Response) -> dict:
    username = data.username.strip()
    ip = request.client.host if request.client else ""
    key = f"{ip}:{username}"
    if is_login_blocked(key):
        raise HTTPException(
            status_code=429,
            detail="尝试次数过多，请 15 分钟后再试",
            headers={"Retry-After": "900"},
        )
    user = authenticate(username, data.password)
    if not user:
        record_login_failure(key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    clear_login_failures(key)
    token = create_session(user.username)
    response.set_cookie(
        TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        secure=_cookie_secure_flag(),
    )
    return {"ok": True, "username": user.username}


@router.post("/logout")
def logout(
    response: Response,
    token_cookie: str = "",
) -> dict:
    destroy_session(token_cookie)
    response.delete_cookie(TOKEN_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(username: str = Depends(current_user)) -> dict:
    return {"username": username}


@router.post("/password")
def password(
    data: ChangePasswordRequest,
    username: str = Depends(current_user),
) -> dict:
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    try:
        change_password(username, data.old_password, data.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}
