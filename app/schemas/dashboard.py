from datetime import datetime

from pydantic import BaseModel, ConfigDict
from app.schemas.base import AppBaseModel


class APDViolationStat(BaseModel):
    apd: str
    violation_count: int
    compliance_percentage: float


class DashboardSummary(BaseModel):
    total_sessions: int
    total_workers: int
    compliance_rate: float
    violations_by_apd: list[APDViolationStat]
    monitored_workers: int | None = None
    violating_workers: int | None = None
    full_apd_workers: int | None = None
    per_apd: dict[str, dict[str, float]] | None = None
    active_cameras: int | None = None
    total_cameras: int | None = None


class ComplianceTrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    total_workers: int
    compliant: int
    violations: int
    rate: float
    time: str | None = None
    label: str | None = None


class WorkerRecordItem(AppBaseModel):
    id: int
    session_id: int
    worker_id: str | None = None
    frame_idx: int | None = None
    track_id: int | None = None
    camera_code: str | None = None
    location: str | None = None
    person_conf: float | None = None
    helm_worn: bool | None = None
    glove_worn: bool | None = None
    sepatu_worn: bool | None = None
    kacamata_worn: bool | None = None
    is_compliant: bool
    detected_at: datetime | None = None
    status: str | None = None
    missing_apd: str | None = None
    handled_at: datetime | None = None
    handled_by: str | None = None
    handling_note: str | None = None