"""可视化插件接口：CRUD、生成、装配/卸载。"""

from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..bot_manager import bot_manager
from ..deps import current_user
from ..process_manager import process_manager
from ..visual_plugin import (
    CONDITION_OPS,
    MESSAGE_TYPES,
    NODE_CATALOG,
    VisualPlugin,
    create_visual_plugin,
    delete_visual_plugin,
    generate_code,
    get_visual_plugin,
    install_to_bot,
    list_visual_plugins,
    uninstall_from_bot,
    update_visual_plugin,
)


router = APIRouter(prefix="/api/visual-plugins", tags=["visual-plugins"])


class CreateRequest(BaseModel):
    name: str
    description: str = ""


class UpdateRequest(BaseModel):
    name: str
    description: str = ""
    flow: Dict


class InstallRequest(BaseModel):
    bot_id: str


def _get(plugin_id: str) -> VisualPlugin:
    plugin = get_visual_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="可视化插件不存在")
    return plugin


@router.get("/catalog")
def catalog(_: str = Depends(current_user)) -> dict:
    return {
        "nodes": NODE_CATALOG,
        "condition_ops": CONDITION_OPS,
        "message_types": MESSAGE_TYPES,
    }


@router.get("")
def list_plugins(_: str = Depends(current_user)) -> dict:
    return {"plugins": list_visual_plugins()}


@router.post("", status_code=201)
def create_plugin(data: CreateRequest, _: str = Depends(current_user)) -> dict:
    try:
        plugin = create_visual_plugin(data.name, data.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plugin.model_dump()


@router.get("/{plugin_id}")
def get_plugin(plugin_id: str, _: str = Depends(current_user)) -> dict:
    return _get(plugin_id).model_dump()


@router.put("/{plugin_id}")
def update_plugin(
    plugin_id: str, data: UpdateRequest, _: str = Depends(current_user)
) -> dict:
    try:
        plugin = update_visual_plugin(plugin_id, data.name, data.description, data.flow)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="可视化插件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plugin.model_dump()


@router.delete("/{plugin_id}")
def delete_plugin(plugin_id: str, _: str = Depends(current_user)) -> dict:
    try:
        delete_visual_plugin(plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="可视化插件不存在") from exc
    return {"ok": True}


@router.post("/{plugin_id}/generate")
def generate(plugin_id: str, _: str = Depends(current_user)) -> dict:
    plugin = _get(plugin_id)
    try:
        code = generate_code(plugin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"filename": f"{plugin.module}.py", "code": code}


@router.post("/{plugin_id}/install")
def install(plugin_id: str, data: InstallRequest, _: str = Depends(current_user)) -> dict:
    bot = bot_manager.get_bot(data.bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="机器人不存在")
    try:
        result = install_to_bot(plugin_id, data.bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="可视化插件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    restarted = False
    if process_manager.is_running(data.bot_id):
        try:
            process_manager.restart(data.bot_id)
            restarted = True
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500, detail=f"插件已写入，但重启失败：{exc}"
            ) from exc
    return {**result, "restarted": restarted}


@router.post("/{plugin_id}/uninstall")
def uninstall(plugin_id: str, data: InstallRequest, _: str = Depends(current_user)) -> dict:
    bot = bot_manager.get_bot(data.bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="机器人不存在")
    try:
        result = uninstall_from_bot(plugin_id, data.bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="可视化插件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    restarted = False
    if process_manager.is_running(data.bot_id):
        try:
            process_manager.restart(data.bot_id)
            restarted = True
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500, detail=f"插件已移除，但重启失败：{exc}"
            ) from exc
    return {**result, "restarted": restarted}
