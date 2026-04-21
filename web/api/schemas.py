"""Pydantic request/response models for the WebUI API."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# --- Clips ---


class ClipAssetSchema(BaseModel):
    path: str
    asset_type: str
    frame_count: int


class ClipSchema(BaseModel):
    name: str
    root_path: str
    state: str
    input_asset: ClipAssetSchema | None = None
    alpha_asset: ClipAssetSchema | None = None
    mask_asset: ClipAssetSchema | None = None
    frame_count: int = 0
    completed_frames: int = 0
    has_outputs: bool = False
    warnings: list[str] = []
    error_message: str | None = None
    folder_name: str | None = None
    project_name: str | None = None


class FolderSchema(BaseModel):
    name: str
    display_name: str
    clips: list[ClipSchema] = []


class ClipListResponse(BaseModel):
    clips: list[ClipSchema]
    clips_dir: str


# --- Jobs ---


class InferenceParamsSchema(BaseModel):
    input_is_linear: bool = False
    despill_strength: float = Field(1.0, ge=0.0, le=1.0)
    auto_despeckle: bool = True
    despeckle_size: int = Field(400, ge=1)
    refiner_scale: float = Field(1.0, ge=0.0)


class OutputConfigSchema(BaseModel):
    fg_enabled: bool = True
    fg_format: str = "exr"
    matte_enabled: bool = True
    matte_format: str = "exr"
    comp_enabled: bool = True
    comp_format: str = "png"
    processed_enabled: bool = True
    processed_format: str = "exr"


# Maximum clip names per request — prevents DoS via massive job submissions
_MAX_CLIPS = 100


class ExtractJobRequest(BaseModel):
    clip_names: list[str] = Field(max_length=_MAX_CLIPS)


class PipelineJobRequest(BaseModel):
    """Full pipeline: extract (if needed) → GVM alpha → inference."""

    clip_names: list[str] = Field(max_length=_MAX_CLIPS)
    alpha_method: str = "gvm"  # "gvm" or "videomama"
    params: InferenceParamsSchema = InferenceParamsSchema()
    output_config: OutputConfigSchema = OutputConfigSchema()
    preset_id: str | None = None


class InferenceJobRequest(BaseModel):
    clip_names: list[str] = Field(max_length=_MAX_CLIPS)
    params: InferenceParamsSchema = InferenceParamsSchema()
    output_config: OutputConfigSchema = OutputConfigSchema()
    frame_range: tuple[int, int] | None = None
    preset_id: str | None = None


class GVMJobRequest(BaseModel):
    clip_names: list[str] = Field(max_length=_MAX_CLIPS)


class VideoMaMaJobRequest(BaseModel):
    clip_names: list[str] = Field(max_length=_MAX_CLIPS)
    chunk_size: int = Field(50, ge=1, le=1000)


class JobSchema(BaseModel):
    id: str
    job_type: str
    clip_name: str
    status: str
    current_frame: int = 0
    total_frames: int = 0
    error_message: str | None = None
    claimed_by: str | None = None
    started_at: float = 0
    completed_at: float = 0
    duration_seconds: float = 0
    fps: float = 0
    priority: int = 0
    shard_group: str | None = None
    shard_index: int = 0
    shard_total: int = 1
    org_id: str | None = None
    submitted_by: str | None = None
    queue_position: int | None = None  # position in queue (1-based), None if not queued
    estimated_wait_seconds: float | None = None  # estimated seconds until this job starts


class JobListResponse(BaseModel):
    current: JobSchema | None = None  # first running job (backward compat)
    running: list[JobSchema] = []  # all running jobs
    queued: list[JobSchema] = []
    history: list[JobSchema] = []


# --- System ---


class DeviceResponse(BaseModel):
    device: str


class VRAMResponse(BaseModel):
    total: float = 0.0
    reserved: float = 0.0
    allocated: float = 0.0
    free: float = 0.0
    name: str = ""
    available: bool = False


# --- WebSocket ---


class WSMessage(BaseModel):
    type: str
    data: dict


# --- Presets ---

_MAX_PRESET_NAME = 100
_MAX_PRESET_DESC = 500


def _strip_html(value: str) -> str:
    """Strip HTML tags from user-provided text (defense-in-depth)."""
    return re.sub(r"<[^>]*>", "", value)


class PresetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=_MAX_PRESET_NAME)
    description: str = Field("", max_length=_MAX_PRESET_DESC)
    params: InferenceParamsSchema = InferenceParamsSchema()
    output_config: OutputConfigSchema = OutputConfigSchema()
    is_default: bool = False

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_html(cls, v: str) -> str:
        return _strip_html(v) if isinstance(v, str) else v


class PresetUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=_MAX_PRESET_NAME)
    description: str | None = Field(None, max_length=_MAX_PRESET_DESC)
    params: InferenceParamsSchema | None = None
    output_config: OutputConfigSchema | None = None
    is_default: bool | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_html(cls, v: str | None) -> str | None:
        return _strip_html(v) if isinstance(v, str) else v


class PresetSchema(BaseModel):
    id: str
    name: str
    description: str = ""
    scope: Literal["org"]
    org_id: str | None = None
    params: InferenceParamsSchema = InferenceParamsSchema()
    output_config: OutputConfigSchema = OutputConfigSchema()
    is_default: bool = False
    created_by: str | None = None
    created_at: float = 0


class PresetListResponse(BaseModel):
    presets: list[PresetSchema] = []
