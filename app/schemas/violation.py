from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.base import AppBaseModel


class ViolationHandleRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)


class ViolationResponse(AppBaseModel):
    id: int
    worker_id: str
    worker_role: Optional[str] = None
    status: str  # "open" | "handled"
    missing_apd: list[str]
    camera_code: Optional[str] = None
    location: Optional[str] = None
    confidence: Optional[float] = None
    snapshot_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    detected_at: datetime
    handled_at: Optional[datetime] = None
    handled_by: Optional[str] = None
    handling_note: Optional[str] = None
    worker_record_id: Optional[int] = None
    session_id: Optional[int] = None


class ViolationListResponse(BaseModel):
    total: int
    items: list[ViolationResponse]
