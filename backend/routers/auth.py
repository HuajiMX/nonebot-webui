"""认证相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from ..deps import TOKEN_COOKIE, current_user
from ..models import ChangePasswordRequest, LoginRequest, SetupRequest
from ..security import (
    authenticate,
    change_password,
    create_session,
    create_user,
    destroy_session,
    has_users,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status() -> dict:
    """是否已初始化（无用户时前端展示首次设置页）。"""
    return {"initialized": has_users()}


@router.post("/setup")
def setup(data: SetupRequest) -> dict:
    if has_users():
        raise HTTPException(status_code=400, detail="系统已初始化，不能重复设置")
    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    create_user(username, data.password)
    token = create_session(username)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    return resp


@router.post("/login")
def login(data: LoginRequest, response: Response) -> dict:
    user = authenticate(data.username.strip(), data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_session(user.username)
    response.set_cookie(
        TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
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
