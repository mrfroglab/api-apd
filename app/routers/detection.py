import json
from datetime import datetime, timezone
from app.core.time import get_now, to_iso_with_tz
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_current_user_optional
from app.database import get_db
from app.models.camera import Camera
from app.models.session import DetectionSession
from app.models.user import User
from app.models.violation import Violation
from app.models.worker import WorkerRecord
from app.services.ws_manager import ws_manager
from app.schemas.detection import (
    ImageDetectionResponse,
    SessionDetailResponse,
    SessionListItem,
    StreamFrameRequest,
    StreamFrameResponse,
    VideoDetectionResponse,
    WorkerRecordResponse,
)
from app.services.ml_client import (
    call_ml_image,
    call_ml_stream_frame,
    call_ml_video,
)

router = APIRouter(prefix="/detect", tags=["detection"])


async def _resolve_camera(camera_code: Optional[str], request: Request, db: AsyncSession):
    code = camera_code
    if not code:
        code = request.query_params.get("camera_code")
    if not code:
        try:
            form = await request.form()
            code = form.get("camera_code")
        except Exception:
            pass
    location = None
    if code:
        cam = (await db.execute(select(Camera).where(Camera.code == code))).scalar_one_or_none()
        if cam:
            location = cam.location
    return code, location


async def _lookup_worker_role(db: AsyncSession, worker_id: str) -> Optional[str]:
    """Ambil jabatan pekerja dari riwayat pelanggaran sebelumnya (None jika belum dikenal)."""
    stmt = (
        select(Violation.worker_role)
        .where(
            Violation.worker_id == worker_id,
            Violation.worker_role.is_not(None),
            Violation.worker_role != "Worker",
        )
        .order_by(Violation.detected_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _violation_event(v: Violation, missing_list: list[str]) -> dict:
    return {
        "type": "violation",
        "id": v.id,
        "worker_id": v.worker_id,
        "worker_role": v.worker_role,
        "camera_code": v.camera_code,
        "location": v.location,
        "missing_apd": missing_list,
        "status": "open",
        "confidence": v.confidence,
        "detected_at": to_iso_with_tz(v.detected_at),
    }


@router.post("/image", response_model=ImageDetectionResponse)
async def detect_image(
    request: Request,
    file: UploadFile = File(...),
    camera_code: Optional[str] = Query(None),
    overlap_threshold: Optional[float] = Query(None, ge=0.0, le=1.0),
    person_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    helm_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    glove_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    sepatu_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    kacamata_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    enable_head_zoom: Optional[bool] = Query(None),
    roi_active: Optional[bool] = Query(None),
    roi_x1: Optional[float] = Query(None),
    roi_y1: Optional[float] = Query(None),
    roi_x2: Optional[float] = Query(None),
    roi_y2: Optional[float] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Upload gambar, forward ke ml-apd, simpan sesi ke database, dan kembalikan hasil deteksi."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File gambar kosong",
        )

    params = {
        "overlap_threshold": overlap_threshold,
        "person_conf": person_conf,
        "helm_conf": helm_conf,
        "glove_conf": glove_conf,
        "sepatu_conf": sepatu_conf,
        "kacamata_conf": kacamata_conf,
        "enable_head_zoom": enable_head_zoom,
        "roi_active": roi_active,
        "roi_x1": roi_x1,
        "roi_y1": roi_y1,
        "roi_x2": roi_x2,
        "roi_y2": roi_y2,
    }

    ml_result = await call_ml_image(
        file_bytes=file_bytes,
        filename=file.filename or "uploaded_image.jpg",
        content_type=file.content_type or "image/jpeg",
        params=params,
    )

    workers_data = ml_result.get("workers", [])
    helm_violations = 0
    glove_violations = 0
    sepatu_violations = 0
    kacamata_violations = 0

    for w in workers_data:
        checklist = w.get("checklist", {})
        if checklist:
            if not checklist.get("helm", True):
                helm_violations += 1
            if not checklist.get("glove", True):
                glove_violations += 1
            if not checklist.get("sepatu", True):
                sepatu_violations += 1
            if not checklist.get("kacamata", True):
                kacamata_violations += 1

    cam_code, cam_location = await _resolve_camera(camera_code, request, db)
    session = DetectionSession(
        session_code=ml_result.get("session_code"),
        source_type="image",
        filename=file.filename,
        annotated_output_path=ml_result.get("annotated_image_url"),
        camera_code=cam_code,
        location=cam_location,
        total_frames=1,
        total_workers_detected=ml_result.get("total_workers", len(workers_data)),
        compliant_workers_count=ml_result.get("compliant_workers_count", 0),
        non_compliant_workers_count=ml_result.get("non_compliant_workers_count", 0),
        compliance_rate=float(ml_result.get("compliance_rate", 0.0)),
        helm_violations=helm_violations,
        glove_violations=glove_violations,
        sepatu_violations=sepatu_violations,
        kacamata_violations=kacamata_violations,
    )
    db.add(session)
    await db.flush()

    pending_events: list[dict] = []
    for w in workers_data:
        bbox = w.get("bbox", {})
        checklist = w.get("checklist", {})
        missing_list = []
        if checklist:
            for apd_name in ["helm", "kacamata", "glove", "sepatu"]:
                if checklist.get(apd_name) is False:
                    missing_list.append(apd_name)
        is_comp = bool(w.get("is_compliant", False))
        w_track = w.get("track_id")
        worker_rec = WorkerRecord(
            session_id=session.id,
            frame_idx=0,
            track_id=w_track,
            worker_id=f"W-{w_track}" if w_track else None,
            camera_code=cam_code,
            location=cam_location,
            bbox_x1=bbox.get("x1") if isinstance(bbox, dict) else None,
            bbox_y1=bbox.get("y1") if isinstance(bbox, dict) else None,
            bbox_x2=bbox.get("x2") if isinstance(bbox, dict) else None,
            bbox_y2=bbox.get("y2") if isinstance(bbox, dict) else None,
            person_conf=w.get("person_conf"),
            helm_worn=checklist.get("helm") if checklist else None,
            glove_worn=checklist.get("glove") if checklist else None,
            sepatu_worn=checklist.get("sepatu") if checklist else None,
            kacamata_worn=checklist.get("kacamata") if checklist else None,
            is_compliant=is_comp,
            status="open" if not is_comp else None,
            missing_apd=json.dumps(missing_list) if not is_comp else None,
            detection_details=json.dumps(w),
        )
        db.add(worker_rec)
        await db.flush()

        if not is_comp:
            v_worker_id = f"W-{w_track}" if w_track else f"W-{worker_rec.id}"
            v_rec = Violation(
                worker_record_id=worker_rec.id,
                session_id=session.id,
                worker_id=v_worker_id,
                worker_role=await _lookup_worker_role(db, v_worker_id),
                status="open",
                missing_apd=json.dumps(missing_list),
                camera_code=cam_code,
                location=cam_location,
                confidence=w.get("person_conf"),
                snapshot_path=ml_result.get("annotated_image_url"),
                detected_at=get_now(),
            )
            db.add(v_rec)
            await db.flush()
            pending_events.append(_violation_event(v_rec, missing_list))

    await db.commit()
    await db.refresh(session)

    # Broadcast setelah commit agar FE tidak menerima ID pelanggaran yang batal tersimpan
    for evt in pending_events:
        await ws_manager.broadcast(evt, camera_code=cam_code)

    response_data = dict(ml_result)
    response_data["session_id"] = session.id
    return ImageDetectionResponse(**response_data)


@router.post("/video", response_model=VideoDetectionResponse)
async def detect_video(
    request: Request,
    file: UploadFile = File(...),
    camera_code: Optional[str] = Query(None),
    sample_stride: Optional[int] = Query(None, ge=1),
    overlap_threshold: Optional[float] = Query(None, ge=0.0, le=1.0),
    person_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    helm_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    glove_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    sepatu_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    kacamata_conf: Optional[float] = Query(None, ge=0.0, le=1.0),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Upload video, forward ke ml-apd, simpan sesi ke database, dan kembalikan hasil deteksi."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File video kosong",
        )

    params = {
        "sample_stride": sample_stride,
        "overlap_threshold": overlap_threshold,
        "person_conf": person_conf,
        "helm_conf": helm_conf,
        "glove_conf": glove_conf,
        "sepatu_conf": sepatu_conf,
        "kacamata_conf": kacamata_conf,
    }

    ml_result = await call_ml_video(
        file_bytes=file_bytes,
        filename=file.filename or "uploaded_video.mp4",
        content_type=file.content_type or "video/mp4",
        params=params,
    )
    cam_code, cam_location = await _resolve_camera(camera_code, request, db)

    session = DetectionSession(
        session_code=ml_result.get("session_code"),
        source_type="video",
        filename=file.filename,
        annotated_output_path=ml_result.get("annotated_video_url"),
        camera_code=cam_code,
        location=cam_location,
        total_frames=ml_result.get("total_frames_processed", 0),
        total_workers_detected=ml_result.get("total_unique_workers", 0),
        compliant_workers_count=ml_result.get("compliant_workers_count", 0),
        non_compliant_workers_count=ml_result.get("non_compliant_workers_count", 0),
        compliance_rate=float(ml_result.get("overall_compliance_rate", 0.0)),
        helm_violations=ml_result.get("helm_violations", 0),
        glove_violations=ml_result.get("glove_violations", 0),
        sepatu_violations=ml_result.get("sepatu_violations", 0),
        kacamata_violations=ml_result.get("kacamata_violations", 0),
    )
    db.add(session)
    await db.flush()

    pending_events: list[dict] = []
    workers_summary = ml_result.get("workers_summary", [])
    for w in workers_summary:
        is_comp = bool(w.get("is_compliant", False))
        checklist = w.get("checklist") or {}
        missing_list = []
        if isinstance(checklist, dict):
            for apd_name in ["helm", "kacamata", "glove", "sepatu"]:
                if checklist.get(apd_name) is False:
                    missing_list.append(apd_name)
        w_track = w.get("track_id")
        worker_rec = WorkerRecord(
            session_id=session.id,
            track_id=w_track,
            worker_id=f"W-{w_track}" if w_track else None,
            camera_code=cam_code,
            location=cam_location,
            helm_worn=checklist.get("helm") if isinstance(checklist, dict) else w.get("helm_worn"),
            glove_worn=checklist.get("glove") if isinstance(checklist, dict) else w.get("glove_worn"),
            sepatu_worn=checklist.get("sepatu") if isinstance(checklist, dict) else w.get("sepatu_worn"),
            kacamata_worn=checklist.get("kacamata") if isinstance(checklist, dict) else w.get("kacamata_worn"),
            is_compliant=is_comp,
            status="open" if not is_comp else None,
            missing_apd=json.dumps(missing_list) if not is_comp else None,
            detection_details=json.dumps(w),
        )
        db.add(worker_rec)
        await db.flush()

        if not is_comp:
            v_worker_id = f"W-{w_track}" if w_track else f"W-{worker_rec.id}"
            v_rec = Violation(
                worker_record_id=worker_rec.id,
                session_id=session.id,
                worker_id=v_worker_id,
                worker_role=await _lookup_worker_role(db, v_worker_id),
                status="open",
                missing_apd=json.dumps(missing_list),
                camera_code=cam_code,
                location=cam_location,
                confidence=w.get("person_conf"),
                snapshot_path=ml_result.get("annotated_video_url"),
                detected_at=get_now(),
            )
            db.add(v_rec)
            await db.flush()
            pending_events.append(_violation_event(v_rec, missing_list))

    await db.commit()
    await db.refresh(session)

    # Broadcast setelah commit agar FE tidak menerima ID pelanggaran yang batal tersimpan
    for evt in pending_events:
        await ws_manager.broadcast(evt, camera_code=cam_code)

    response_data = dict(ml_result)
    response_data["session_id"] = session.id
    return VideoDetectionResponse(**response_data)


@router.post("/stream-frame", response_model=StreamFrameResponse)
async def detect_stream_frame(payload: StreamFrameRequest):
    """Forward frame base64 ke ml-apd dan kembalikan hasil deteksi langsung tanpa simpan ke DB."""
    ml_payload = {
        "client_id": payload.client_id,
        "session_code": payload.session_code,
        "frame_base64": payload.frame_base64,
    }
    result = await call_ml_stream_frame(ml_payload)
    cam_code = payload.camera_code or payload.session_code
    now_iso = to_iso_with_tz(get_now())
    await ws_manager.broadcast({
        "type": "detection",
        "camera_code": cam_code,
        "ts": now_iso,
        "total_workers": result.get("total_workers", 0),
        "compliant_workers": result.get("compliant_workers", 0),
        "non_compliant_workers": result.get("non_compliant_workers", 0),
        "workers": result.get("workers", []),
        "fps": result.get("fps"),
    }, camera_code=cam_code)
    return StreamFrameResponse(**result)


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mengambil daftar histori sesi deteksi."""
    stmt = select(DetectionSession)
    if source_type:
        stmt = stmt.where(DetectionSession.source_type == source_type)
    stmt = stmt.order_by(desc(DetectionSession.created_at)).offset(skip).limit(limit)

    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return sessions


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mengambil detail lengkap sesi deteksi beserta catatan worker."""
    stmt = (
        select(DetectionSession)
        .options(selectinload(DetectionSession.workers))
        .where(DetectionSession.id == session_id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesi deteksi {session_id} tidak ditemukan",
        )

    workers_res = [WorkerRecordResponse.model_validate(w) for w in session.workers]
    detail = SessionDetailResponse(
        id=session.id,
        session_code=session.session_code,
        source_type=session.source_type,
        filename=session.filename,
        annotated_output_path=session.annotated_output_path,
        total_frames=session.total_frames,
        total_workers_detected=session.total_workers_detected,
        compliant_workers_count=session.compliant_workers_count,
        non_compliant_workers_count=session.non_compliant_workers_count,
        compliance_rate=session.compliance_rate,
        helm_violations=session.helm_violations,
        glove_violations=session.glove_violations,
        sepatu_violations=session.sepatu_violations,
        kacamata_violations=session.kacamata_violations,
        summary_notes=session.summary_notes,
        created_at=session.created_at,
        workers=workers_res,
    )
    return detail


@router.delete("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Menghapus sesi deteksi berdasarkan ID."""
    stmt = select(DetectionSession).where(DetectionSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesi deteksi {session_id} tidak ditemukan",
        )

    await db.delete(session)
    await db.commit()
    return {"message": f"Sesi deteksi {session_id} berhasil dihapus"}
