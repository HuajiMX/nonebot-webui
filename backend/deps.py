"""FastAPI 公共依赖：认证、WebSocket 认证。"""

from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, WebSocket, WebSocketException, status

from .security import validate_session


TOKEN_COOKIE = "nb_webui_token"


def current_user(
    authorization: str = Header(default=""),
    token_cookie: str = Cookie(default="", alias=TOKEN_COOKIE),
) -> str:
    """校验登录态，返回用户名。"""
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = token_cookie
    username = validate_session(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或会话已过期")
    return username


async def ws_auth(
    websocket: WebSocket,
) -> str:
    """WebSocket 认证：优先 query token，其次 Cookie。"""
    token = websocket.query_params.get("token", "")
    if not token:
        token = websocket.cookies.get(TOKEN_COOKIE, "")
    username = validate_session(token)
    if not username:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="未认证")
    return username
