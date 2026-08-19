"""数据模型定义。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


NAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]+$")


class User(BaseModel):
    username: str
    password_hash: str
    salt: str
    created_at: str = ""
    updated_at: str = ""


class Bot(BaseModel):
    """机器人记录。"""

    id: str
    name: str
    directory: str
    adapter: str = "onebot_v11"
    host: str = "0.0.0.0"
    port: int = 8080
    python: str = ""
    venv: str = ""
    plugin_dir: str = "src/plugins"
    status: str = "stopped"  # creating/starting/running/stopping/stopped/error
    pid: Optional[int] = None
    terminal_command: str = ""
    auto_start: bool = False
    managed: bool = True  # 是否由 WebUI 生成脚手架（true 时支持插件启停过滤加载）
    created_at: str = ""
    updated_at: str = ""
    extra: Dict[str, Any] = Field(default_factory=dict)


class BotCreate(BaseModel):
    name: str
    directory: str
    adapter: str = "onebot_v11"
    host: str = "0.0.0.0"
    port: int = 8080
    python: str = ""
    create_dir: bool = True
    plugin_dir: str = "src/plugins"
    auto_start: bool = False

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("机器人名称不能为空")
        if not NAME_RE.match(v):
            raise ValueError("名称仅支持字母、数字、下划线、中划线、中文")
        if len(v) > 64:
            raise ValueError("名称过长")
        return v

    @field_validator("directory")
    @classmethod
    def _check_dir(cls, v: str) -> str:
        v = v.strip().strip('"').strip("'")
        if not v:
            raise ValueError("目录不能为空")
        return v

    @field_validator("port")
    @classmethod
    def _check_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("端口范围应为 1-65535")
        return v


class BotUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    terminal_command: Optional[str] = None
    auto_start: Optional[bool] = None
    plugin_dir: Optional[str] = None
    adapter: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("机器人名称不能为空")
        if not NAME_RE.match(v):
            raise ValueError("名称仅支持字母、数字、下划线、中划线、中文")
        if len(v) > 64:
            raise ValueError("名称过长")
        return v

    @field_validator("host")
    @classmethod
    def _check_host(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("监听地址不能为空")
        return v

    @field_validator("port")
    @classmethod
    def _check_port(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not (1 <= v <= 65535):
            raise ValueError("端口范围应为 1-65535")
        return v

    @field_validator("plugin_dir")
    @classmethod
    def _check_plugin_dir(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().strip('"').strip("'")
        if not v:
            raise ValueError("插件目录不能为空")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ConfigUpdate(BaseModel):
    """机器人 .env 配置更新。"""

    content: str


class TerminalCommandRequest(BaseModel):
    command: str = ""
