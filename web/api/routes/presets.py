"""Preset CRUD API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import get_current_user
from ..org_isolation import resolve_org_id
from ..presets import create_preset, delete_preset, get_preset, list_presets, update_preset
from ..schemas import PresetCreateRequest, PresetListResponse, PresetSchema, PresetUpdateRequest
from ..tier_guard import require_member

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/presets", tags=["presets"], dependencies=[Depends(require_member)])


@router.get("", response_model=PresetListResponse)
def list_all_presets(request: Request):
    org_id = resolve_org_id(request)
    return PresetListResponse(presets=list_presets(org_id))


@router.get("/{preset_id}", response_model=PresetSchema)
def get_single_preset(preset_id: str, request: Request):
    org_id = resolve_org_id(request)
    preset = get_preset(preset_id, org_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@router.post("", response_model=PresetSchema, status_code=201)
def create_new_preset(req: PresetCreateRequest, request: Request):
    org_id = resolve_org_id(request)
    if not org_id:
        raise HTTPException(status_code=400, detail="No active organisation")
    user = get_current_user(request)
    try:
        preset = create_preset(
            org_id=org_id,
            name=req.name,
            description=req.description,
            params=req.params,
            output_config=req.output_config,
            is_default=req.is_default,
            created_by=user.user_id if user else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return preset


@router.patch("/{preset_id}", response_model=PresetSchema)
def update_existing_preset(preset_id: str, req: PresetUpdateRequest, request: Request):
    org_id = resolve_org_id(request)
    if not org_id:
        raise HTTPException(status_code=400, detail="No active organisation")
    updated = update_preset(
        preset_id,
        org_id,
        name=req.name,
        description=req.description,
        params=req.params,
        output_config=req.output_config,
        is_default=req.is_default,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Preset not found")
    return updated


@router.delete("/{preset_id}", status_code=204)
def delete_existing_preset(preset_id: str, request: Request):
    org_id = resolve_org_id(request)
    if not org_id:
        raise HTTPException(status_code=400, detail="No active organisation")
    if not delete_preset(preset_id, org_id):
        raise HTTPException(status_code=404, detail="Preset not found")
