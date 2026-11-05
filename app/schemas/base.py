from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer
from app.core.time import to_app_tz


class AppBaseModel(BaseModel):
    """Base schema untuk seluruh model respon.

    Mengonversi semua field bertipe datetime ke ISO 8601 dengan offset zona waktu (APP_TZ).
    """
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", mode="wrap", check_fields=False)
    def serialize_datetimes(self, value, nxt):
        if isinstance(value, datetime):
            loc = to_app_tz(value)
            return loc.isoformat() if loc else None
        return nxt(value)
