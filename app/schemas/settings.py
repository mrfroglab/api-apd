from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.base import AppBaseModel


class ROIConfig(BaseModel):
    active: bool = False
    x1: float = Field(0.0, ge=0, le=1)
    y1: float = Field(0.0, ge=0, le=1)
    x2: float = Field(1.0, ge=0, le=1)
    y2: float = Field(1.0, ge=0, le=1)


class ThresholdsConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overlap_threshold: float = Field(0.3, ge=0, le=1)
    person_conf: float = Field(0.5, ge=0, le=1)
    helm_conf: float = Field(0.5, ge=0, le=1)
    glove_conf: float = Field(0.4, ge=0, le=1)
    sepatu_conf: float = Field(0.4, ge=0, le=1)
    kacamata_conf: float = Field(0.35, ge=0, le=1)
    enable_head_zoom: bool = True
    head_crop_ratio: float = Field(0.35, gt=0, le=1)
    head_zoom_conf: float = Field(0.4, ge=0, le=1)
    enable_temporal_persistence: bool = True
    temporal_memory_frames: int = Field(5, ge=1, le=60)
    sampling_fps: int = Field(5, ge=1, le=60)
    alarm_delay_s: int = Field(10, ge=0, le=300)
    iou_threshold: float = Field(0.45, ge=0, le=1)


class SettingsResponse(AppBaseModel):
    roi: ROIConfig
    thresholds: ThresholdsConfig
    sampling_fps: int = 5
    alarm_delay_s: int = 10
    iou_threshold: float = 0.45
    updated_at: datetime


class SettingsUpdateRequest(BaseModel):
    """Partial update: kirim hanya field yang ingin diubah."""
    roi: ROIConfig | None = None
    thresholds: ThresholdsConfig | None = None
    sampling_fps: int | None = Field(default=None, ge=1, le=60)
    alarm_delay_s: int | None = Field(default=None, ge=0, le=300)
    iou_threshold: float | None = Field(default=None, ge=0, le=1)