from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Violation(Base):
    __tablename__ = "violations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    worker_record_id = Column(
        Integer,
        ForeignKey("worker_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id = Column(
        Integer,
        ForeignKey("detection_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    worker_id = Column(String(50), nullable=False)  # e.g. "W-104"
    worker_role = Column(String(100), nullable=True)  # e.g. "Roustabout"
    status = Column(String(20), default="open", nullable=False)  # "open" | "handled"
    missing_apd = Column(Text, nullable=False)  # JSON string e.g. ["kacamata"]
    camera_code = Column(String(50), nullable=True)  # e.g. "CAM-01"
    location = Column(String(100), nullable=True)  # e.g. "Drill Floor"
    confidence = Column(Float, nullable=True)
    snapshot_path = Column(String(500), nullable=True)
    detected_at = Column(DateTime, nullable=False)
    handled_at = Column(DateTime, nullable=True)
    handled_by = Column(String(150), nullable=True)  # "1: Akmal Manggala" or name
    handling_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    worker_record = relationship("WorkerRecord", foreign_keys=[worker_record_id])
    session = relationship("DetectionSession", foreign_keys=[session_id])
