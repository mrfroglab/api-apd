from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------- Request (query params / body yang diteruskan ke ml-apd) ----------

class _ThresholdParams(BaseModel):
    """Parameter umum. None = pakai nilai dari tabel system_settings."""
    overlap_threshold: float | None = Field(default=None, ge=0, le=1)
    person_conf: float | None = Field(default=None, ge=0, le=1)
    helm_conf: float | None = Field(default=None, ge=0, le=1)
    glove_conf: float | None = Field(default=None, ge=0, le=1)
    sepatu_conf: float | None = Field(default=None, ge=0, le=1)
    kacamata_conf: float | None = Field(default=None, ge=0, le=1)


class ImageDetectRequest(_ThresholdParams):
    enable_head_zoom: bool | None = None
    roi_active: bool | None = None
    roi_x1: float | None = None
    roi_y1: float | None = None
    roi_x2: float | None = None
    roi_y2: float | None = None


class VideoDetectRequest(_ThresholdParams):
    sample_stride: int | None = Field(default=None, ge=1)


class StreamFrameRequest(BaseModel):
    client_id: str
    session_code: str
    frame_base64: str


# ---------- Response ke FE ----------

class ImageDetectionResponse(BaseModel):
    session_id: int | None = None  # None kalau user tidak login / tidak disimpan
    session_code: str
    total_workers: int
    compliant_workers_count: int
    non_compliant_workers_count: int
    compliance_rate: float
    workers: list[dict[str, Any]] = []  # TODO: rapikan setelah struktur worker dari ml-apd pasti
    all_detected_apds: list[Any] = []
    annotated_image_url: str | None = None
    annotated_image_base64: str | None = None
    inference_time_ms: float | None = None
    two_stage_zoom_applied: bool | None = None


class VideoDetectionResponse(BaseModel):
    session_id: int | None = None
    session_code: str
    total_frames_processed: int
    total_unique_workers: int
    compliant_workers_count: int
    non_compliant_workers_count: int
    overall_compliance_rate: float
    helm_violations: int = 0
    glove_violations: int = 0
    sepatu_violations: int = 0
    kacamata_violations: int = 0
    annotated_video_url: str | None = None
    annotated_sample_frames: list[Any] = []
    processing_time_sec: float | None = None
    workers_summary: list[dict[str, Any]] = []
    status: str


class StreamFrameResponse(BaseModel):
    client_id: str
    session_code: str
    frame_idx: int
    total_workers: int
    compliant_workers: int
    non_compliant_workers: int
    workers: list[dict[str, Any]] = []
    annotated_frame_base64: str | None = None
    fps: float | None = None


# ---------- Histori sesi (dibaca dari database) ----------

class WorkerRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    frame_idx: int | None = None
    track_id: int | None = None
    bbox_x1: float | None = None
    bbox_y1: float | None = None
    bbox_x2: float | None = None
    bbox_y2: float | None = None
    person_conf: float | None = None
    helm_worn: bool | None = None
    glove_worn: bool | None = None
    sepatu_worn: bool | None = None
    kacamata_worn: bool | None = None
    is_compliant: bool
    detection_details: str | None = None  # JSON dalam bentuk teks
    detected_at: datetime | None = None


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_code: str
    source_type: str
    filename: str | None = None
    total_workers_detected: int
    compliant_workers_count: int
    non_compliant_workers_count: int
    compliance_rate: float
    created_at: datetime


class SessionDetailResponse(SessionListItem):
    annotated_output_path: str | None = None
    total_frames: int | None = None
    helm_violations: int = 0
    glove_violations: int = 0
    sepatu_violations: int = 0
    kacamata_violations: int = 0
    summary_notes: str | None = None
    workers: list[WorkerRecordResponse] = []