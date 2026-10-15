from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer

from app.database import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)  # selalu 1

    roi_active = Column(Boolean, default=False, nullable=False)
    roi_x1 = Column(Float, default=0.0, nullable=False)
    roi_y1 = Column(Float, default=0.0, nullable=False)
    roi_x2 = Column(Float, default=1.0, nullable=False)
    roi_y2 = Column(Float, default=1.0, nullable=False)

    overlap_threshold = Column(Float, default=0.3, nullable=False)
    person_conf = Column(Float, default=0.5, nullable=False)
    helm_conf = Column(Float, default=0.5, nullable=False)
    glove_conf = Column(Float, default=0.4, nullable=False)
    sepatu_conf = Column(Float, default=0.4, nullable=False)
    kacamata_conf = Column(Float, default=0.35, nullable=False)

    enable_head_zoom = Column(Boolean, default=True, nullable=False)
    head_crop_ratio = Column(Float, default=0.35, nullable=False)
    head_zoom_conf = Column(Float, default=0.4, nullable=False)

    enable_temporal_persistence = Column(Boolean, default=True, nullable=False)
    temporal_memory_frames = Column(Integer, default=5, nullable=False)

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )