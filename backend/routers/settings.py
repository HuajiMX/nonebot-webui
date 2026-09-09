"""系统设置接口：邮件（SMTP）配置。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import mailer
from ..deps import current_user


router = APIRouter(prefix="/api/settings", tags=["settings"])


class EmailConfigPayload(BaseModel):
    enabled: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    security: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    from_addr: Optional[str] = None
    from_name: Optional[str] = None
    recipients: Optional[List[str]] = None
    timeout: Optional[int] = None


class EmailTestPayload(BaseModel):
    to: List[str] = Field(default_factory=list)
    config: Optional[EmailConfigPayload] = None


@router.get("/email")
def get_email(_: str = Depends(current_user)) -> dict:
    """读取邮件配置（密码以掩码返回）。"""
    return mailer.get_public_email_config()


@router.put("/email")
def update_email(data: EmailConfigPayload, _: str = Depends(current_user)) -> dict:
    """保存邮件配置。"""
    try:
        return mailer.save_email_config(data.model_dump(exclude_unset=True))
    except mailer.EmailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/email/test")
def test_email(data: EmailTestPayload, _: str = Depends(current_user)) -> dict:
    """发送测试邮件；可携带未保存的表单配置进行验证。"""
    try:
        override = (
            data.config.model_dump(exclude_unset=True) if data.config is not None else None
        )
        recipients = mailer.test_email(config_override=override, to=data.to)
    except mailer.EmailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "recipients": recipients}
