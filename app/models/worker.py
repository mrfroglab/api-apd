from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class WorkerRecord(Base):
    __tablename__ = "worker_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("detection_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frame_idx = Column(Integer, nullable=True)
    track_id = Column(Integer, nullable=True)

    bbox_x1 = Column(Float, nullable=True)
    bbox_y1 = Column(Float, nullable=True)
    bbox_x2 = Column(Float, nullable=True)
    bbox_y2 = Column(Float, nullable=True)
    person_conf = Column(Float, nullable=True)

    helm_worn = Column(Boolean, nullable=True)
    glove_worn = Column(Boolean, nullable=True)
    sepatu_worn = Column(Boolean, nullable=True)
    kacamata_worn = Column(Boolean, nullable=True)

    is_compliant = Column(Boolean, default=False, nullable=False)
    detection_details = Column(Text, nullable=True)  # JSON text
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("DetectionSession", back_populates="workers")
