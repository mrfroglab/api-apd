import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def get_app_tz() -> ZoneInfo:
    tz_name = os.getenv("APP_TZ", "Asia/Jakarta")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("Asia/Jakarta")


def get_now() -> datetime:
    """Mengembalikan waktu saat ini dalam UTC.

    Jika env PMLD_DEMO_NOW diset (misal: '2026-11-04T10:42:18+07:00'),
    nilai tersebut di-parse dan dikonversi ke UTC sebagai titik acuan 'sekarang'.
    """
    demo_now = os.getenv("PMLD_DEMO_NOW")
    if demo_now:
        try:
            dt = datetime.fromisoformat(demo_now)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=get_app_tz())
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)

now = get_now


def to_app_tz(dt: datetime | None) -> datetime | None:
    """Konversi datetime (disimpan sebagai UTC di DB) ke zona waktu aplikasi (APP_TZ)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_app_tz())


def to_iso_with_tz(dt: datetime | None) -> str | None:
    """Format datetime ke ISO 8601 lengkap dengan offset zona waktu aplikasi."""
    localized = to_app_tz(dt)
    return localized.isoformat() if localized else None


def to_utc(dt: datetime | None) -> datetime | None:
    """Konversi datetime lokal/naive ke timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_app_tz())
    return dt.astimezone(timezone.utc)
