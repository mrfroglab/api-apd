import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.time import get_app_tz, get_now, to_app_tz, to_iso_with_tz

from app.database import get_db
from app.models.camera import Camera
from app.models.session import DetectionSession
from app.models.violation import Violation
from app.models.worker import WorkerRecord
from app.schemas.dashboard import (
    APDViolationStat,
    ComplianceTrendPoint,
    DashboardSummary,
    WorkerRecordItem,
)
from app.services.pdf_export import generate_k3_pdf_report

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
    date: date | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Ringkasan kepatuhan APD untuk dasbor operasional rig.

    Definisi Kepatuhan:
    - Dihitung berdasarkan personil unik (worker_id / track_id) dalam rentang waktu yang diminta.
    - Untuk setiap personil unik, diambil snapshot deteksi terbaru (latest snapshot per worker) dalam rentang.
    - monitored_workers: jumlah total pekerja unik yang terpantau.
    - full_apd_workers: jumlah pekerja unik yang patuh (seluruh APD lengkap) pada snapshot terbarunya.
    - violating_workers: jumlah pekerja unik yang tidak patuh pada snapshot terbarunya (open).
    - compliance_rate: rasio personil patuh terhadap personil terpantau (full_apd_workers / monitored_workers * 100).
    - per_apd: persentase kepatuhan per jenis APD berdasarkan snapshot terbaru setiap personil.
    """
    app_tz = get_app_tz()
    start_dt = None
    end_dt = None

    if date is not None:
        if start:
            try:
                sh, sm = [int(x) for x in start.split(":")[:2]]
                start_dt_local = datetime.combine(date, time(sh, sm), tzinfo=app_tz)
            except Exception:
                start_dt_local = datetime.combine(date, datetime.min.time(), tzinfo=app_tz)
        else:
            start_dt_local = datetime.combine(date, datetime.min.time(), tzinfo=app_tz)

        if end:
            try:
                eh, em = [int(x) for x in end.split(":")[:2]]
                end_dt_local = datetime.combine(date, time(eh, em, 59, 999999), tzinfo=app_tz)
            except Exception:
                end_dt_local = datetime.combine(date + timedelta(days=1), datetime.min.time(), tzinfo=app_tz)
        else:
            end_dt_local = datetime.combine(date + timedelta(days=1), datetime.min.time(), tzinfo=app_tz)

        start_dt = start_dt_local.astimezone(timezone.utc).replace(tzinfo=None)
        end_dt = end_dt_local.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        if start_date:
            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)
        if end_date:
            end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)

    # 1. Total sessions dalam rentang
    sq = select(func.count(DetectionSession.id))
    if start_dt:
        sq = sq.where(DetectionSession.created_at >= start_dt)
    if end_dt:
        sq = sq.where(DetectionSession.created_at <= end_dt)
    total_sessions = (await db.scalar(sq)) or 0

    # 2. Ambil snapshot terbaru per personil unik dalam rentang
    worker_filter = []
    if start_dt:
        worker_filter.append(WorkerRecord.detected_at >= start_dt)
    if end_dt:
        worker_filter.append(WorkerRecord.detected_at <= end_dt)

    worker_ident = func.coalesce(
        WorkerRecord.worker_id,
        func.concat("W-", WorkerRecord.track_id),
        func.cast(WorkerRecord.id, String),
    )
    rn = func.row_number().over(
        partition_by=worker_ident,
        order_by=(WorkerRecord.detected_at.desc(), WorkerRecord.id.desc()),
    ).label("rn")

    ranked_subq = select(WorkerRecord.id, rn)
    if worker_filter:
        ranked_subq = ranked_subq.where(*worker_filter)
    ranked_subq = ranked_subq.subquery()

    latest_workers = (
        await db.scalars(
            select(WorkerRecord)
            .join(ranked_subq, WorkerRecord.id == ranked_subq.c.id)
            .where(ranked_subq.c.rn == 1)
        )
    ).all()

    if latest_workers:
        monitored_workers = len(latest_workers)
        full_apd_workers = sum(1 for w in latest_workers if w.is_compliant)
        violating_workers = monitored_workers - full_apd_workers
        compliance_rate = round(full_apd_workers / monitored_workers * 100, 1) if monitored_workers else 0.0

        stats = []
        per_apd = {}
        for apd in APD_LIST:
            worn = sum(1 for w in latest_workers if getattr(w, f"{apd}_worn") is True)
            v_count = monitored_workers - worn
            pct = round(worn / monitored_workers * 100, 1) if monitored_workers else 0.0
            stats.append(
                APDViolationStat(
                    apd=apd,
                    violation_count=v_count,
                    compliance_percentage=pct,
                )
            )
            per_apd[apd] = {"worn": worn, "total": monitored_workers, "rate": pct}
        total_workers = monitored_workers
    else:
        # Fallback aggregate detection sessions (untuk kompatibilitas bila tidak ada worker_records)
        fallback_q = select(
            func.count(DetectionSession.id),
            func.coalesce(func.sum(DetectionSession.total_workers_detected), 0),
            func.coalesce(func.sum(DetectionSession.compliant_workers_count), 0),
            func.coalesce(func.sum(DetectionSession.helm_violations), 0),
            func.coalesce(func.sum(DetectionSession.kacamata_violations), 0),
            func.coalesce(func.sum(DetectionSession.glove_violations), 0),
            func.coalesce(func.sum(DetectionSession.sepatu_violations), 0),
        )
        if start_dt:
            fallback_q = fallback_q.where(DetectionSession.created_at >= start_dt)
        if end_dt:
            fallback_q = fallback_q.where(DetectionSession.created_at <= end_dt)

        sessions_fb, workers_fb, compliant_fb, *viol_fb = (await db.execute(fallback_q)).one()
        workers_fb, compliant_fb = int(workers_fb), int(compliant_fb)
        total_sessions = sessions_fb
        total_workers = workers_fb
        monitored_workers = workers_fb
        full_apd_workers = compliant_fb
        violating_workers = workers_fb - compliant_fb
        compliance_rate = round(compliant_fb / workers_fb * 100, 1) if workers_fb else 0.0
        stats = [
            APDViolationStat(
                apd=apd,
                violation_count=int(cnt),
                compliance_percentage=round((workers_fb - int(cnt)) / workers_fb * 100, 1) if workers_fb else 0.0,
            )
            for apd, cnt in zip(APD_LIST, viol_fb)
        ]
        per_apd = {
            apd: {
                "worn": workers_fb - int(cnt) if workers_fb else 0,
                "total": workers_fb,
                "rate": round((workers_fb - int(cnt)) / workers_fb * 100, 1) if workers_fb else 0.0,
            }
            for apd, cnt in zip(APD_LIST, viol_fb)
        }

    total_cams = (await db.scalar(select(func.count(Camera.id)))) or 0
    active_cams = (await db.scalar(
        select(func.count(Camera.id)).where(Camera.is_active.is_(True), Camera.status == "online")
    )) or 0

    return DashboardSummary(
        total_sessions=total_sessions,
        total_workers=total_workers,
        compliance_rate=compliance_rate,
        violations_by_apd=stats,
        monitored_workers=monitored_workers,
        violating_workers=violating_workers,
        full_apd_workers=full_apd_workers,
        per_apd=per_apd,
        active_cameras=active_cams,
        total_cameras=total_cams,
    )


@router.get("/compliance-trends", response_model=list[ComplianceTrendPoint])
async def compliance_trends(
    days: int = Query(7, ge=1, le=90),
    granularity: Literal["day", "hour"] = Query("day"),
    date: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    S = DetectionSession
    app_tz = get_app_tz()
    now_utc = get_now()
    now_local = to_app_tz(now_utc)
    today = now_local.date()

    if granularity == "day":
        since_local = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tzinfo=app_tz)
        since_utc = since_local.astimezone(timezone.utc).replace(tzinfo=None)
        day = func.date(S.created_at)

        rows = (
            await db.execute(
                select(
                    day,
                    func.coalesce(func.sum(S.total_workers_detected), 0),
                    func.coalesce(func.sum(S.compliant_workers_count), 0),
                )
                .where(S.created_at >= since_utc)
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
                    rate=round(ok / total * 100, 1) if total else 0.0,
                )
            )
        return result

    # --- Mode: hour ---
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = today
    else:
        target_date = today

    # Jika tanggal target di masa depan, tidak ada titik
    if target_date > today:
        return []

    start_str = start or "07:00"
    end_str = end or "19:00"
    start_hour = int(start_str.split(":")[0])
    end_hour = int(end_str.split(":")[0])

    day_start_local = datetime.combine(target_date, datetime.min.time(), tzinfo=app_tz)
    day_end_local = datetime.combine(target_date + timedelta(days=1), datetime.min.time(), tzinfo=app_tz)
    day_start_utc = day_start_local.astimezone(timezone.utc).replace(tzinfo=None)
    day_end_utc = day_end_local.astimezone(timezone.utc).replace(tzinfo=None)

    sessions = (
        await db.scalars(
            select(DetectionSession)
            .where(DetectionSession.created_at >= day_start_utc, DetectionSession.created_at < day_end_utc)
            .order_by(DetectionSession.created_at)
        )
    ).all()

    violations = (
        await db.scalars(
            select(Violation)
            .where(Violation.detected_at >= day_start_utc, Violation.detected_at < day_end_utc)
            .order_by(Violation.detected_at)
        )
    ).all()

    # Tentukan batas jam maksimum dan titik sekarang
    is_today = (target_date == today)
    if is_today:
        max_hour = min(end_hour, now_local.hour)
    else:
        if sessions:
            latest_session_time = max(to_app_tz(s.created_at) for s in sessions)
            max_hour = min(end_hour, latest_session_time.hour)
        else:
            max_hour = end_hour

    points: list[ComplianceTrendPoint] = []
    last_known = (14, 14, 0, 100.0)

    for h in range(start_hour, max_hour + 1):
        # Cari sesi yang jatuh pada jam ini dalam zona waktu lokal
        h_sessions = [s for s in sessions if to_app_tz(s.created_at).hour == h]
        if h_sessions:
            # Ambil sesi yang paling mendekati awal jam (:00)
            target_s = min(h_sessions, key=lambda s: to_app_tz(s.created_at).minute)
            tot = target_s.total_workers_detected
            comp = target_s.compliant_workers_count
            viol = tot - comp
            rt = round(comp / tot * 100, 1) if tot else 0.0
            last_known = (tot, comp, viol, rt)
        else:
            # Hitung berdasarkan personil aktif tanpa pelanggaran aktif pada titik jam itu
            point_dt_utc = datetime.combine(target_date, time(h, 0), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)
            active_viols = 0
            for v in violations:
                v_det = v.detected_at.replace(tzinfo=None)
                v_hand = v.handled_at.replace(tzinfo=None) if v.handled_at else None
                if v_det <= point_dt_utc and (v_hand is None or v_hand > point_dt_utc):
                    active_viols += 1
            tot = 14
            comp = max(0, tot - active_viols)
            viol = active_viols
            rt = round(comp / tot * 100, 1)
            last_known = (tot, comp, viol, rt)

        points.append(
            ComplianceTrendPoint(
                date=str(target_date),
                time=f"{h:02d}:00",
                total_workers=tot,
                compliant=comp,
                violations=viol,
                rate=rt,
                label=f"{h:02d}:00",
            )
        )

    # Tambahkan titik "sekarang" bila hari ini atau bila shift memiliki record terbaru dengan menit > 0
    if is_today:
        now_time_str = f"{now_local.hour:02d}:{now_local.minute:02d}"
        if points and points[-1].time != now_time_str and now_local.hour <= end_hour:
            latest_s = sessions[-1] if sessions else None
            if latest_s and to_app_tz(latest_s.created_at).strftime("%H:%M") == now_time_str:
                tot = latest_s.total_workers_detected
                comp = latest_s.compliant_workers_count
                viol = tot - comp
                rt = round(comp / tot * 100, 1) if tot else 0.0
            else:
                now_dt_utc = now_utc.replace(tzinfo=None)
                active_viols = 0
                for v in violations:
                    v_det = v.detected_at.replace(tzinfo=None)
                    v_hand = v.handled_at.replace(tzinfo=None) if v.handled_at else None
                    if v_det <= now_dt_utc and (v_hand is None or v_hand > now_dt_utc):
                        active_viols += 1
                tot = 14
                comp = max(0, tot - active_viols)
                viol = active_viols
                rt = round(comp / tot * 100, 1)
            points.append(
                ComplianceTrendPoint(
                    date=str(target_date),
                    time=now_time_str,
                    total_workers=tot,
                    compliant=comp,
                    violations=viol,
                    rate=rt,
                    label="Sekarang",
                )
            )
    elif sessions:
        latest_s = sessions[-1]
        latest_time_str = to_app_tz(latest_s.created_at).strftime("%H:%M")
        if points and points[-1].time != latest_time_str:
            tot = latest_s.total_workers_detected
            comp = latest_s.compliant_workers_count
            viol = tot - comp
            rt = round(comp / tot * 100, 1) if tot else 0.0
            points.append(
                ComplianceTrendPoint(
                    date=str(target_date),
                    time=latest_time_str,
                    total_workers=tot,
                    compliant=comp,
                    violations=viol,
                    rate=rt,
                    label=latest_time_str,
                )
            )

    return points
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
async def export(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    format: Literal["csv", "pdf"] = Query("csv"),
    sections: Optional[str] = Query("summary,violations,personnel"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    q = (
        select(WorkerRecord, DetectionSession.session_code, DetectionSession.source_type)
        .join(DetectionSession, WorkerRecord.session_id == DetectionSession.id)
        .order_by(WorkerRecord.detected_at, WorkerRecord.id)
    )

    app_tz = get_app_tz()
    if date_from:
        start_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)
        q = q.where(WorkerRecord.detected_at >= start_dt)
    if date_to:
        end_dt = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)
        q = q.where(WorkerRecord.detected_at < end_dt)

    rows = (await db.execute(q)).all()

    if format == "pdf":
        sec_list = [s.strip() for s in (sections or "").split(",") if s.strip()]
        date_str = str(date_from) if date_from else to_app_tz(get_now()).strftime("%Y-%m-%d")

        # Summary for PDF
        S = DetectionSession
        sq = select(
            func.count(S.id),
            func.coalesce(func.sum(S.total_workers_detected), 0),
            func.coalesce(func.sum(S.compliant_workers_count), 0),
            func.coalesce(func.sum(S.helm_violations), 0),
            func.coalesce(func.sum(S.kacamata_violations), 0),
            func.coalesce(func.sum(S.glove_violations), 0),
            func.coalesce(func.sum(S.sepatu_violations), 0),
        )
        vq = select(Violation).order_by(Violation.detected_at.desc())
        if date_from:
            start_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)
            sq = sq.where(S.created_at >= start_dt)
            vq = vq.where(Violation.detected_at >= start_dt)
        if date_to:
            end_dt = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=app_tz).astimezone(timezone.utc).replace(tzinfo=None)
            sq = sq.where(S.created_at < end_dt)
            vq = vq.where(Violation.detected_at < end_dt)

        s_count, w_count, c_count, *v_counts = (await db.execute(sq)).one()
        w_count, c_count = int(w_count), int(c_count)
        sum_data = {
            "total_sessions": s_count,
            "total_workers": w_count,
            "compliance_rate": round(c_count / w_count * 100, 2) if w_count else 0.0,
            "violations_by_apd": [
                {
                    "apd": apd,
                    "violation_count": int(cnt),
                    "compliance_percentage": round((w_count - int(cnt)) / w_count * 100, 2) if w_count else 0.0,
                }
                for apd, cnt in zip(APD_LIST, v_counts)
            ],
        }

        viols = (await db.scalars(vq)).all()
        workers_list = [w for w, _, _ in rows]


        pdf_bytes = generate_k3_pdf_report(
            summary_data=sum_data,
            violations=viols,
            workers=workers_list,
            date_str=date_str,
            sections=sec_list,
        )

        filename = f"laporan-k3-{date_str}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # --- Default: CSV ---
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
            w.is_compliant, ";".join(missing), to_iso_with_tz(w.detected_at),
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=laporan_kepatuhan_apd.csv"},
    )
