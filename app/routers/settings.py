from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user_optional
from app.database import get_db
from app.models.system_settings import SystemSettings
from app.schemas.settings import (
    ROIConfig,
    SettingsResponse,
    SettingsUpdateRequest,
    ThresholdsConfig,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


async def get_or_create_settings(db: AsyncSession) -> SystemSettings:
    s = await db.get(SystemSettings, 1)
    if s is None:
        s = SystemSettings(id=1)
        db.add(s)
        await db.commit()
        await db.refresh(s)
    return s


def to_response(s: SystemSettings) -> SettingsResponse:
    return SettingsResponse(
        roi=ROIConfig(active=s.roi_active, x1=s.roi_x1, y1=s.roi_y1, x2=s.roi_x2, y2=s.roi_y2),
        thresholds=ThresholdsConfig.model_validate(s),
        updated_at=s.updated_at,
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    return to_response(await get_or_create_settings(db))


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    s = await get_or_create_settings(db)

    if body.roi is not None:
        for key, val in body.roi.model_dump(exclude_unset=True).items():
            setattr(s, f"roi_{key}", val)
        if s.roi_x1 >= s.roi_x2 or s.roi_y1 >= s.roi_y2:
            await db.rollback()
            raise HTTPException(status_code=400, detail="ROI tidak valid: x1 < x2 dan y1 < y2")

    if body.thresholds is not None:
        for key, val in body.thresholds.model_dump(exclude_unset=True).items():
            setattr(s, key, val)

    await db.commit()
    await db.refresh(s)
    return to_response(s)