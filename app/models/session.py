from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class DetectionSession(Base):
    __tablename__ = "detection_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_code = Column(String(50), unique=True, index=True, nullable=False)
    source_type = Column(String(20), nullable=False)  # "image", "video", "stream"
    filename = Column(String(255), nullable=True)
    annotated_output_path = Column(String(500), nullable=True)

    total_frames = Column(Integer, default=1, nullable=False)
    total_workers_detected = Column(Integer, default=0, nullable=False)
    compliant_workers_count = Column(Integer, default=0, nullable=False)
    non_compliant_workers_count = Column(Integer, default=0, nullable=False)
    compliance_rate = Column(Float, default=0.0, nullable=False)

    helm_violations = Column(Integer, default=0, nullable=False)
    glove_violations = Column(Integer, default=0, nullable=False)
    sepatu_violations = Column(Integer, default=0, nullable=False)
    kacamata_violations = Column(Integer, default=0, nullable=False)

    summary_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    workers = relationship(
        "WorkerRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
