import json
from datetime import datetime, timezone
from app.core.time import get_now, to_app_tz, to_iso_with_tz
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.camera import Camera, CameraROI
from app.models.user import User
from app.schemas.camera import (
    CameraCreate,
    CameraResponse,
    CameraROIItem,
    CameraROIResponse,
    CameraUpdate,
)
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def resolve_camera_status(camera: Camera) -> CameraResponse:
    now = get_now()
    status_str = camera.status
    disconnected_since = camera.disconnected_since
    disconnected_since_at = camera.disconnected_since_at

    if not camera.is_active:
        status_str = "offline"
        if disconnected_since_at is None:
            disconnected_since_at = camera.created_at
        if not disconnected_since:
            disconnected_since = to_app_tz(disconnected_since_at).strftime("%H:%M:%S")
    elif camera.last_seen_at is not None:
        last_seen = camera.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        diff = (now - last_seen).total_seconds()
        if diff > 30:
            status_str = "offline"
            if disconnected_since_at is None:
                disconnected_since_at = last_seen
            if not disconnected_since:
                disconnected_since = to_app_tz(disconnected_since_at).strftime("%H:%M:%S")
    elif status_str == "offline":
        if disconnected_since_at is None:
            disconnected_since_at = camera.created_at
        if not disconnected_since:
            disconnected_since = to_app_tz(disconnected_since_at).strftime("%H:%M:%S")

    if status_str == "online":
        disconnected_since = None
        disconnected_since_at = None

    return CameraResponse(
        id=camera.id,
        code=camera.code,
        name=camera.name,
        location=camera.location,
        is_active=camera.is_active,
        status=status_str,
        last_seen_at=camera.last_seen_at,
        fps=camera.fps,
        disconnected_since=disconnected_since,
        disconnected_since_at=disconnected_since_at,
        created_at=camera.created_at,
    )


@router.get("", response_model=List[CameraResponse])
async def list_cameras(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).order_by(Camera.code)
    result = await db.execute(stmt)
    cameras = result.scalars().all()
    return [resolve_camera_status(cam) for cam in cameras]


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    body: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.code == body.code)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Kode kamera '{body.code}' sudah terdaftar",
        )

    now = get_now()
    camera = Camera(
        code=body.code,
        name=body.name,
        location=body.location,
        is_active=body.is_active,
        status="online",
        last_seen_at=now,
        fps=body.fps,
        disconnected_since=None,
        disconnected_since_at=None,
        created_at=now,
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    return resolve_camera_status(camera)


@router.get("/{code}", response_model=CameraResponse)
async def get_camera(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.code == code)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kamera dengan kode '{code}' tidak ditemukan",
        )
    return resolve_camera_status(camera)


@router.patch("/{code}", response_model=CameraResponse)
async def update_camera(
    code: str,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.code == code)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kamera dengan kode '{code}' tidak ditemukan",
        )

    old_status = camera.status
    if body.name is not None:
        camera.name = body.name
    if body.location is not None:
        camera.location = body.location
    if body.is_active is not None:
        camera.is_active = body.is_active
    if body.fps is not None:
        camera.fps = body.fps
    if body.status is not None:
        camera.status = body.status
        if body.status == "offline":
            now_utc = get_now()
            camera.disconnected_since_at = now_utc
            camera.disconnected_since = to_app_tz(now_utc).strftime("%H:%M:%S")
        elif body.status == "online":
            camera.disconnected_since = None
            camera.disconnected_since_at = None
    await db.commit()
    await db.refresh(camera)

    resolved = resolve_camera_status(camera)
    if resolved.status != old_status:
        await ws_manager.broadcast({
            "type": "camera_status",
            "camera_code": camera.code,
            "status": resolved.status,
            "disconnected_since": resolved.disconnected_since,
        }, camera_code=camera.code)

    return resolved


@router.post("/{code}/heartbeat", response_model=CameraResponse)
async def camera_heartbeat(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.code == code)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kamera dengan kode '{code}' tidak ditemukan",
        )

    old_status = camera.status
    camera.last_seen_at = get_now()
    camera.status = "online"
    camera.disconnected_since = None
    camera.disconnected_since_at = None
    await db.refresh(camera)

    if old_status != "online":
        await ws_manager.broadcast({
            "type": "camera_status",
            "camera_code": camera.code,
            "status": "online",
            "disconnected_since": None,
        }, camera_code=camera.code)

    return resolve_camera_status(camera)


# ---------- ROI endpoints ----------

def serialize_roi(roi: CameraROI) -> CameraROIResponse:
    pts = json.loads(roi.points) if isinstance(roi.points, str) else roi.points
    req = json.loads(roi.required_apd) if isinstance(roi.required_apd, str) else roi.required_apd
    return CameraROIResponse(
        id=roi.id,
        camera_code=roi.camera_code,
        name=roi.name,
        points=pts,
        kind=roi.kind,
        required_apd=req,
        updated_at=roi.updated_at,
    )


@router.get("/{code}/rois", response_model=List[CameraROIResponse])
async def get_camera_rois(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.code == code)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kamera dengan kode '{code}' tidak ditemukan",
        )

    stmt_rois = select(CameraROI).where(CameraROI.camera_code == code).order_by(CameraROI.id)
    rois = (await db.scalars(stmt_rois)).all()
    return [serialize_roi(r) for r in rois]


@router.put("/{code}/rois", response_model=List[CameraROIResponse])
async def replace_camera_rois(
    code: str,
    rois_in: List[CameraROIItem],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.code == code)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kamera dengan kode '{code}' tidak ditemukan",
        )

    # Delete existing ROIs
    existing = (await db.scalars(select(CameraROI).where(CameraROI.camera_code == code))).all()
    for ex in existing:
        await db.delete(ex)

    now = get_now()
    new_rois = []
    for item in rois_in:
        roi = CameraROI(
            camera_code=code,
            name=item.name,
            points=json.dumps(item.points),
            kind=item.kind,
            required_apd=json.dumps(item.required_apd),
            updated_at=now,
        )
        db.add(roi)
        new_rois.append(roi)

    await db.commit()
    for r in new_rois:
        await db.refresh(r)

    return [serialize_roi(r) for r in new_rois]


@router.delete("/{code}/rois/{roi_id}", status_code=status.HTTP_200_OK)
async def delete_camera_roi(
    code: str,
    roi_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(CameraROI).where(CameraROI.camera_code == code, CameraROI.id == roi_id)
    result = await db.execute(stmt)
    roi = result.scalar_one_or_none()
    if not roi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ROI {roi_id} pada kamera '{code}' tidak ditemukan",
        )

    await db.delete(roi)
    await db.commit()
    return {"message": f"ROI {roi_id} berhasil dihapus"}
