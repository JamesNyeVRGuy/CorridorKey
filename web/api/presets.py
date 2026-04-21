from __future__ import annotations

import logging
import os
import threading
import time
import uuid

from .database import get_storage
from .schemas import InferenceParamsSchema, OutputConfigSchema, PresetSchema

logger = logging.getLogger(__name__)

_STORAGE_KEY = "presets"
_MAX_PRESETS_PER_ORG = int(os.environ.get("CK_MAX_PRESETS_PER_ORG", "50").strip())
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Org-level preset CRUD
# ---------------------------------------------------------------------------


def _load_org_presets(org_id: str) -> dict[str, dict]:
    """Load org presets dict from storage."""
    all_presets: dict[str, dict[str, dict]] = get_storage().get_setting(_STORAGE_KEY, {})
    return all_presets.get(org_id, {})


def _save_org_presets(org_id: str, presets: dict[str, dict]) -> None:
    """Persist org presets dict to storage."""
    all_presets: dict[str, dict[str, dict]] = get_storage().get_setting(_STORAGE_KEY, {})
    all_presets[org_id] = presets
    get_storage().set_setting(_STORAGE_KEY, all_presets)


def list_presets(org_id: str | None) -> list[PresetSchema]:
    """Return all presets for an org."""
    if not org_id:
        return []
    presets = [PresetSchema(**data) for data in _load_org_presets(org_id).values()]
    return sorted(presets, key=lambda p: (not p.is_default, p.name.lower()))


def get_preset(preset_id: str, org_id: str | None) -> PresetSchema | None:
    """Fetch a single preset by ID."""
    if not org_id:
        return None
    org_presets = _load_org_presets(org_id)
    if preset_id in org_presets:
        return PresetSchema(**org_presets[preset_id])
    return None


def create_preset(
    org_id: str,
    name: str,
    description: str,
    params: InferenceParamsSchema,
    output_config: OutputConfigSchema,
    is_default: bool,
    created_by: str | None,
) -> PresetSchema:
    """Create a new org-level preset."""
    with _lock:
        org_presets = _load_org_presets(org_id)

        if len(org_presets) >= _MAX_PRESETS_PER_ORG:
            raise ValueError(f"Maximum of {_MAX_PRESETS_PER_ORG} presets per organisation reached")

        preset_id = f"org-{uuid.uuid4().hex[:12]}"
        preset = PresetSchema(
            id=preset_id,
            name=name,
            description=description,
            scope="org",
            org_id=org_id,
            params=params,
            output_config=output_config,
            is_default=is_default,
            created_by=created_by,
            created_at=time.time(),
        )

        if is_default:
            for p in org_presets.values():
                p["is_default"] = False

        org_presets[preset_id] = preset.model_dump()
        _save_org_presets(org_id, org_presets)
    logger.info("Created preset %s (%s) for org %s", preset_id, name, org_id)
    return preset


def update_preset(
    preset_id: str,
    org_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    params: InferenceParamsSchema | None = None,
    output_config: OutputConfigSchema | None = None,
    is_default: bool | None = None,
) -> PresetSchema | None:
    """Update an existing org-level preset. Returns None if not found."""
    with _lock:
        org_presets = _load_org_presets(org_id)
        if preset_id not in org_presets:
            return None
        data = org_presets[preset_id]
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if params is not None:
            data["params"] = params.model_dump()
        if output_config is not None:
            data["output_config"] = output_config.model_dump()
        if is_default is not None:
            if is_default:
                for p in org_presets.values():
                    p["is_default"] = False
            data["is_default"] = is_default

        org_presets[preset_id] = data
        _save_org_presets(org_id, org_presets)
    logger.info("Updated preset %s for org %s", preset_id, org_id)
    return PresetSchema(**data)


def delete_preset(preset_id: str, org_id: str) -> bool:
    """Delete an org-level preset. Returns False if not found."""
    with _lock:
        org_presets = _load_org_presets(org_id)
        if preset_id not in org_presets:
            return False
        del org_presets[preset_id]
        _save_org_presets(org_id, org_presets)
    logger.info("Deleted preset %s from org %s", preset_id, org_id)
    return True
