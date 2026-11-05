from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(50), unique=True, index=True, nullable=False)  # e.g. "CAM-01"
    name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="online", nullable=False)  # "online" | "offline"
    last_seen_at = Column(DateTime, nullable=True)
    fps = Column(Float, default=25.0, nullable=False)
    disconnected_since = Column(String(50), nullable=True)
    disconnected_since_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    rois = relationship(
        "CameraROI",
        back_populates="camera",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CameraROI(Base):
    __tablename__ = "camera_rois"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_code = Column(
        String(50),
        ForeignKey("cameras.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    points = Column(Text, nullable=False)  # JSON string [[x, y], ...] normalized 0..1
    kind = Column(String(30), default="monitor", nullable=False)  # "monitor" | "red_zone"
    required_apd = Column(Text, default="[]", nullable=False)  # JSON string ["helm", ...]
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    camera = relationship("Camera", back_populates="rois")
