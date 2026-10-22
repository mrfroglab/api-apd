import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.session import DetectionSession
from app.models.worker import WorkerRecord
from app.schemas.dashboard import (
    APDViolationStat,
    ComplianceTrendPoint,
    DashboardSummary,
    WorkerRecordItem,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

APD_LIST = ["helm", "kacamata", "glove", "sepatu"]
APD_WORN_COL = {
    "helm": WorkerRecord.helm_worn,
    "glove": WorkerRecord.glove_worn,
    "sepatu": WorkerRecord.sepatu_worn,
    "kacamata": WorkerRecord.kacamata_worn,
}


def _start_of(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    S = DetectionSession
    q = select(
        func.count(S.id),
        func.coalesce(func.sum(S.total_workers_detected), 0),
        func.coalesce(func.sum(S.compliant_workers_count), 0),
        func.coalesce(func.sum(S.helm_violations), 0),
        func.coalesce(func.sum(S.kacamata_violations), 0),
        func.coalesce(func.sum(S.glove_violations), 0),
        func.coalesce(func.sum(S.sepatu_violations), 0),
    )
    if start_date:
        q = q.where(S.created_at >= _start_of(start_date))
    if end_date:
        q = q.where(S.created_at < _start_of(end_date + timedelta(days=1)))

    sessions, workers, compliant, *viol = (await db.execute(q)).one()
    workers, compliant = int(workers), int(compliant)

    stats = [
        APDViolationStat(
            apd=apd,
            violation_count=int(count),
            compliance_percentage=round((workers - int(count)) / workers * 100, 2) if workers else 0.0,
        )
        for apd, count in zip(APD_LIST, viol)
    ]

    return DashboardSummary(
        total_sessions=sessions,
        total_workers=workers,
        compliance_rate=round(compliant / workers * 100, 2) if workers else 0.0,
        violations_by_apd=stats,
    )


@router.get("/compliance-trends", response_model=list[ComplianceTrendPoint])
async def compliance_trends(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    S = DetectionSession
    today = datetime.now(timezone.utc).date()
    since = _start_of(today - timedelta(days=days - 1))
    day = func.date(S.created_at)

    rows = (
        await db.execute(
            select(
                day,
                func.coalesce(func.sum(S.total_workers_detected), 0),
                func.coalesce(func.sum(S.compliant_workers_count), 0),
            )
            .where(S.created_at >= since)
            .group_by(day)
        )
    ).all()
    data = {str(r[0]): (int(r[1]), int(r[2])) for r in rows}

    result = []
    for i in range(days):
        d = str(today - timedelta(days=days - 1 - i))
        total, ok = data.get(d, (0, 0))
        result.append(
            ComplianceTrendPoint(
                date=d,
                total_workers=total,
                compliant=ok,
                violations=total - ok,
                rate=round(ok / total * 100, 2) if total else 0.0,
            )
        )
    return result


@router.get("/worker-records", response_model=list[WorkerRecordItem])
async def worker_records(
    is_compliant: bool | None = None,
    missing_apd: Literal["helm", "glove", "sepatu", "kacamata"] | None = None,
    session_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    q = select(WorkerRecord).order_by(
        WorkerRecord.detected_at.desc(), WorkerRecord.id.desc()
    )
    if is_compliant is not None:
        q = q.where(WorkerRecord.is_compliant.is_(is_compliant))
    if missing_apd:
        q = q.where(APD_WORN_COL[missing_apd].is_(False))
    if session_id is not None:
        q = q.where(WorkerRecord.session_id == session_id)

    return (await db.scalars(q.limit(limit).offset(offset))).all()


@router.get("/export")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(WorkerRecord, DetectionSession.session_code, DetectionSession.source_type)
            .join(DetectionSession, WorkerRecord.session_id == DetectionSession.id)
            .order_by(WorkerRecord.detected_at, WorkerRecord.id)
        )
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "session_code", "source_type", "frame_idx", "track_id",
        "helm", "kacamata", "glove", "sepatu",
        "patuh", "apd_kurang", "detected_at",
    ])
    for w, code, source in rows:
        missing = [a for a in APD_LIST if getattr(w, f"{a}_worn") is False]
        writer.writerow([
            code, source, w.frame_idx, w.track_id,
            w.helm_worn, w.kacamata_worn, w.glove_worn, w.sepatu_worn,
            w.is_compliant, ";".join(missing), w.detected_at,
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=laporan_kepatuhan_apd.csv"},
    )