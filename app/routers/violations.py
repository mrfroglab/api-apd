import json
import os
from datetime import date, datetime, timedelta, timezone
from app.core.time import get_app_tz, get_now, to_iso_with_tz
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.violation import Violation
from app.models.worker import WorkerRecord
from app.schemas.violation import (
    ViolationHandleRequest,
    ViolationListResponse,
    ViolationResponse,
)
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/violations", tags=["Violations"])


def _serialize_violation(v: Violation) -> ViolationResponse:
    if isinstance(v.missing_apd, str):
        try:
            missing_list = json.loads(v.missing_apd)
        except Exception:
            missing_list = [v.missing_apd]
    elif isinstance(v.missing_apd, list):
        missing_list = v.missing_apd
    else:
        missing_list = []

    snap_url = f"/violations/{v.id}/snapshot" if v.snapshot_path else None

    return ViolationResponse(
        id=v.id,
        worker_id=v.worker_id,
        worker_role=v.worker_role,
        status=v.status,
        missing_apd=missing_list,
        camera_code=v.camera_code,
        location=v.location,
        confidence=v.confidence,
        snapshot_path=v.snapshot_path,
        snapshot_url=snap_url,
        detected_at=v.detected_at,
        handled_at=v.handled_at,
        handled_by=v.handled_by,
        handling_note=v.handling_note,
        worker_record_id=v.worker_record_id,
        session_id=v.session_id,
    )


@router.get("", response_model=ViolationListResponse)
async def list_violations(
    status: Optional[str] = Query(None, pattern="^(open|handled)$"),
    camera_code: Optional[str] = Query(None),
    apd: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Violation)

    if status:
        query = query.where(Violation.status == status)
    if camera_code:
        query = query.where(Violation.camera_code == camera_code)
    if apd:
        query = query.where(Violation.missing_apd.like(f"%{apd}%"))
    if date_from:
        start_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=get_app_tz()).astimezone(timezone.utc).replace(tzinfo=None)
        query = query.where(Violation.detected_at >= start_dt)
    if date_to:
        end_dt = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=get_app_tz()).astimezone(timezone.utc).replace(tzinfo=None)
        query = query.where(Violation.detected_at < end_dt)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Violation.worker_id.ilike(pattern),
                Violation.worker_role.ilike(pattern),
                Violation.location.ilike(pattern),
                Violation.handling_note.ilike(pattern),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    records_stmt = query.order_by(Violation.detected_at.desc(), Violation.id.desc()).offset(offset).limit(limit)
    records = (await db.scalars(records_stmt)).all()

    return ViolationListResponse(
        total=total,
        items=[_serialize_violation(v) for v in records],
    )


@router.get("/{id}", response_model=ViolationResponse)
async def get_violation(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Violation).where(Violation.id == id)
    v = (await db.execute(stmt)).scalar_one_or_none()
    if not v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pelanggaran dengan ID {id} tidak ditemukan",
        )
    return _serialize_violation(v)


@router.post("/{id}/handle", response_model=ViolationResponse)
async def handle_violation(
    id: int,
    body: ViolationHandleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Violation).where(Violation.id == id)
    v = (await db.execute(stmt)).scalar_one_or_none()
    if not v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pelanggaran dengan ID {id} tidak ditemukan",
        )

    now = get_now()
    handler_name = user.full_name or user.username

    v.status = "handled"
    v.handled_at = now
    v.handled_by = handler_name
    v.handling_note = body.note

    if v.worker_record_id:
        wr = await db.get(WorkerRecord, v.worker_record_id)
        if wr:
            wr.status = "handled"
            wr.handled_at = now
            wr.handled_by = handler_name
            wr.handling_note = body.note

    await db.commit()
    await db.refresh(v)

    await ws_manager.broadcast({
        "type": "violation_handled",
        "id": v.id,
        "status": "handled",
        "handled_by": v.handled_by,
        "handled_at": to_iso_with_tz(v.handled_at),
        "handling_note": v.handling_note,
    }, camera_code=v.camera_code)

    return _serialize_violation(v)


@router.post("/{id}/reopen", response_model=ViolationResponse)
async def reopen_violation(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Violation).where(Violation.id == id)
    v = (await db.execute(stmt)).scalar_one_or_none()
    if not v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pelanggaran dengan ID {id} tidak ditemukan",
        )

    v.status = "open"
    v.handled_at = None
    v.handled_by = None
    v.handling_note = None

    if v.worker_record_id:
        wr = await db.get(WorkerRecord, v.worker_record_id)
        if wr:
            wr.status = "open"
            wr.handled_at = None
            wr.handled_by = None
            wr.handling_note = None

    await db.commit()
    await db.refresh(v)

    await ws_manager.broadcast({
        "type": "violation_handled",
        "id": v.id,
        "status": "open",
        "handled_by": None,
        "handled_at": None,
        "handling_note": None,
    }, camera_code=v.camera_code)

    return _serialize_violation(v)


@router.get("/{id}/snapshot")
async def get_violation_snapshot(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Violation).where(Violation.id == id)
    v = (await db.execute(stmt)).scalar_one_or_none()
    if not v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pelanggaran dengan ID {id} tidak ditemukan",
        )

    if not v.snapshot_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot bukti tidak tersedia untuk pelanggaran ini",
        )

    clean_path = v.snapshot_path.lstrip("/")
    if os.path.exists(v.snapshot_path):
        target_path = v.snapshot_path
    elif os.path.exists(clean_path):
        target_path = clean_path
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Berkas snapshot bukti tidak ditemukan di server",
        )

    return FileResponse(target_path, media_type="image/jpeg")
