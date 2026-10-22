from datetime import datetime

from pydantic import BaseModel, ConfigDict


class APDViolationStat(BaseModel):
    apd: str
    violation_count: int
    compliance_percentage: float


class DashboardSummary(BaseModel):
    total_sessions: int
    total_workers: int
    compliance_rate: float
    violations_by_apd: list[APDViolationStat]


class ComplianceTrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    total_workers: int
    compliant: int
    violations: int
    rate: float


class WorkerRecordItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    frame_idx: int | None = None
    track_id: int | None = None
    person_conf: float | None = None
    helm_worn: bool | None = None
    glove_worn: bool | None = None
    sepatu_worn: bool | None = None
    kacamata_worn: bool | None = None
    is_compliant: bool
    detected_at: datetime | None = None