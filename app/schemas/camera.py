from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.base import AppBaseModel


class CameraBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True
    fps: float = Field(25.0, ge=0.0, le=120.0)


class CameraCreate(CameraBase):
    code: str = Field(..., min_length=2, max_length=50)


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    fps: Optional[float] = Field(None, ge=0.0, le=120.0)
    status: Optional[str] = Field(None, pattern="^(online|offline)$")


class CameraResponse(CameraBase, AppBaseModel):
    id: int
    code: str
    status: str  # "online" | "offline"
    last_seen_at: Optional[datetime] = None
    disconnected_since: Optional[str] = None
    disconnected_since_at: Optional[datetime] = None
    created_at: datetime

class CameraROIItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    points: list[list[float]] = Field(..., description="Daftar titik poligon [[x, y], ...]")
    kind: str = Field("monitor", pattern="^(monitor|red_zone)$")
    required_apd: list[str] = Field(default_factory=lambda: ["helm", "kacamata", "glove", "sepatu"])

    @field_validator("points")
    @classmethod
    def validate_points(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) < 3:
            raise ValueError("Poligon ROI minimal harus memiliki 3 titik")
        for pt in v:
            if len(pt) != 2:
                raise ValueError(f"Titik ROI harus berupa [x, y], diterima: {pt}")
            x, y = pt[0], pt[1]
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(f"Koordinat titik ROI harus berada dalam rentang 0..1, diterima: [{x}, {y}]")
        return v


class CameraROIResponse(CameraROIItem, AppBaseModel):
    id: int
    camera_code: str
    updated_at: datetime
