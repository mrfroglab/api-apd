import asyncio
import json
import os
from datetime import datetime, timezone
from PIL import Image, ImageDraw

from sqlalchemy import delete, select
from app.core.security import get_password_hash
from app.database import AsyncSessionLocal, Base, engine, run_lightweight_migrations
from app.models.camera import Camera, CameraROI
from app.models.session import DetectionSession
from app.models.user import User
from app.models.violation import Violation
from app.models.worker import WorkerRecord


def _create_dummy_image(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (320, 240), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 310, 230], outline=(222, 100, 59), width=2)
    draw.text((20, 110), f"PDU MIGAS EVIDENCE: {text}", fill=(255, 255, 255))
    img.save(path, format="JPEG")


async def seed():
    print("Inisialisasi database dan migrasi...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_lightweight_migrations(conn)

    async with AsyncSessionLocal() as db:
        print("Menyiapkan user demo...")
        # 1. User demo: hse@pdu.co.id / pmld-demo-2026
        stmt_user = select(User).where(User.email == "hse@pdu.co.id")
        user = (await db.execute(stmt_user)).scalar_one_or_none()
        if not user:
            user = User(
                username="hse@pdu.co.id",
                email="hse@pdu.co.id",
                full_name="Akmal Manggala",
                role="supervisor",
                hashed_password=get_password_hash("pmld-demo-2026"),
                is_active=True,
            )
            db.add(user)
        else:
            user.hashed_password = get_password_hash("pmld-demo-2026")
            user.full_name = "Akmal Manggala"
            user.role = "supervisor"
            user.is_active = True

        print("Menyiapkan 4 kamera...")
        # 2. Kamera demo (CAM-01..CAM-04)
        cameras_data = [
            {
                "code": "CAM-01",
                "name": "CAM-01 Drill Floor (Red Zone)",
                "location": "Drill Floor",
                "is_active": True,
                "status": "online",
                "fps": 25.0,
                "disconnected_since": None,
                "rois": [
                    {
                        "name": "Drill Floor Red Zone",
                        "kind": "red_zone",
                        "points": [[0.17, 0.30], [0.80, 0.24], [0.91, 0.84], [0.10, 0.89]],
                        "required_apd": ["helm", "kacamata", "glove", "sepatu"],
                    }
                ],
            },
            {
                "code": "CAM-02",
                "name": "CAM-02 Mud Pump",
                "location": "Mud Pump",
                "is_active": True,
                "status": "online",
                "fps": 24.8,
                "disconnected_since": None,
                "rois": [
                    {
                        "name": "Mud Pump Monitor Area",
                        "kind": "monitor",
                        "points": [[0.12, 0.25], [0.88, 0.22], [0.84, 0.80], [0.14, 0.82]],
                        "required_apd": ["helm", "kacamata", "glove", "sepatu"],
                    }
                ],
            },
            {
                "code": "CAM-03",
                "name": "CAM-03 Catwalk, Pipe Rack",
                "location": "Catwalk, Pipe Rack",
                "is_active": True,
                "status": "online",
                "fps": 25.0,
                "disconnected_since": None,
                "rois": [
                    {
                        "name": "Catwalk Monitor Area",
                        "kind": "monitor",
                        "points": [[0.20, 0.15], [0.88, 0.15], [0.82, 0.85], [0.15, 0.85]],
                        "required_apd": ["helm", "kacamata", "glove", "sepatu"],
                    }
                ],
            },
            {
                "code": "CAM-04",
                "name": "CAM-04 Substructure",
                "location": "Substructure",
                "is_active": False,
                "status": "offline",
                "fps": 0.0,
                "disconnected_since": "10:35:10",
                "disconnected_since_at": datetime(2026, 11, 4, 3, 35, 10, tzinfo=timezone.utc),
                "rois": [
                    {
                        "name": "Substructure Monitor Area",
                        "kind": "monitor",
                        "points": [[0.12, 0.18], [0.85, 0.20], [0.80, 0.82], [0.15, 0.80]],
                        "required_apd": ["helm", "glove", "sepatu"],
                    }
                ],
            },
        ]

        now = datetime.now(timezone.utc)
        for c_data in cameras_data:
            stmt = select(Camera).where(Camera.code == c_data["code"])
            cam = (await db.execute(stmt)).scalar_one_or_none()
            if not cam:
                cam = Camera(
                    code=c_data["code"],
                    name=c_data["name"],
                    location=c_data["location"],
                    is_active=c_data["is_active"],
                    status=c_data["status"],
                    fps=c_data["fps"],
                    disconnected_since=c_data["disconnected_since"],
                    disconnected_since_at=c_data.get("disconnected_since_at"),
                    last_seen_at=now if c_data["status"] == "online" else None,
                    created_at=now,
                )
                db.add(cam)
            else:
                cam.name = c_data["name"]
                cam.location = c_data["location"]
                cam.is_active = c_data["is_active"]
                cam.status = c_data["status"]
                cam.fps = c_data["fps"]
                cam.disconnected_since = c_data["disconnected_since"]
                cam.disconnected_since_at = c_data.get("disconnected_since_at")
                if c_data["status"] == "online":
                    cam.last_seen_at = now
            await db.flush()

            # Replace ROIs
            await db.execute(delete(CameraROI).where(CameraROI.camera_code == c_data["code"]))
            for r_item in c_data["rois"]:
                roi = CameraROI(
                    camera_code=c_data["code"],
                    name=r_item["name"],
                    points=json.dumps(r_item["points"]),
                    kind=r_item["kind"],
                    required_apd=json.dumps(r_item["required_apd"]),
                    updated_at=now,
                )
                db.add(roi)

        print("Menyiapkan data shift 2026-11-04...")
        demo_codes = [
            "SESSION-20261104-0700",
            "SESSION-20261104-0800",
            "SESSION-20261104-0900",
            "SESSION-20261104-1000",
            "SESSION-20261104-1042",
        ]
        # Clean previous demo sessions to maintain idempotency
        existing_sessions = (await db.scalars(select(DetectionSession).where(DetectionSession.session_code.in_(demo_codes)))).all()
        for es in existing_sessions:
            await db.delete(es)
        await db.execute(delete(Violation).where(Violation.worker_id.in_(["W-104", "W-108", "W-103", "W-109"])))
        await db.flush()

        # Buat dummy snapshot images
        _create_dummy_image("outputs/V-104.jpg", "W-104 KACAMATA")
        _create_dummy_image("outputs/V-108.jpg", "W-108 GLOVE")
        _create_dummy_image("outputs/V-103.jpg", "W-103 GLOVE")
        _create_dummy_image("outputs/V-109.jpg", "W-109 KACAMATA")

        # 3. Buat sesi-sesi shift untuk tren per jam (disimpan dalam UTC, setara WIB)
        # Jam 07:00:12 WIB -> 00:00:12 UTC (14 pekerja, 13 patuh, 1 pelanggaran W-109 kacamata)
        dt_0700 = datetime(2026, 11, 4, 0, 0, 12, tzinfo=timezone.utc)
        s_0700 = DetectionSession(
            session_code="SESSION-20261104-0700",
            source_type="stream",
            total_frames=1,
            total_workers_detected=14,
            compliant_workers_count=13,
            non_compliant_workers_count=1,
            compliance_rate=92.9,
            kacamata_violations=1,
            camera_code="CAM-03",
            location="Catwalk",
            created_at=dt_0700,
        )
        db.add(s_0700)

        # Jam 08:00:00 WIB -> 01:00:00 UTC (14 pekerja, 14 patuh, 0 pelanggaran)
        dt_0800 = datetime(2026, 11, 4, 1, 0, 0, tzinfo=timezone.utc)
        s_0800 = DetectionSession(
            session_code="SESSION-20261104-0800",
            source_type="stream",
            total_frames=1,
            total_workers_detected=14,
            compliant_workers_count=14,
            non_compliant_workers_count=0,
            compliance_rate=100.0,
            camera_code="CAM-01",
            location="Drill Floor",
            created_at=dt_0800,
        )
        db.add(s_0800)

        # Jam 09:00:00 WIB -> 02:00:00 UTC (14 pekerja, 13 patuh, 1 pelanggaran W-103 glove)
        dt_0900 = datetime(2026, 11, 4, 2, 0, 0, tzinfo=timezone.utc)
        s_0900 = DetectionSession(
            session_code="SESSION-20261104-0900",
            source_type="stream",
            total_frames=1,
            total_workers_detected=14,
            compliant_workers_count=13,
            non_compliant_workers_count=1,
            compliance_rate=92.9,
            glove_violations=1,
            camera_code="CAM-03",
            location="Pipe Rack",
            created_at=dt_0900,
        )
        db.add(s_0900)

        # Jam 10:00:00 WIB -> 03:00:00 UTC (14 pekerja, 14 patuh, 0 pelanggaran)
        dt_1000 = datetime(2026, 11, 4, 3, 0, 0, tzinfo=timezone.utc)
        s_1000 = DetectionSession(
            session_code="SESSION-20261104-1000",
            source_type="stream",
            total_frames=1,
            total_workers_detected=14,
            compliant_workers_count=14,
            non_compliant_workers_count=0,
            compliance_rate=100.0,
            camera_code="CAM-02",
            location="Mud Pump",
            created_at=dt_1000,
        )
        db.add(s_1000)

        # Jam 10:42:18 WIB -> 03:42:18 UTC (14 pekerja, 12 patuh, 2 pelanggaran W-104 kacamata & W-108 glove)
        dt_1042 = datetime(2026, 11, 4, 3, 42, 18, tzinfo=timezone.utc)
        s_1042 = DetectionSession(
            session_code="SESSION-20261104-1042",
            source_type="stream",
            total_frames=1,
            total_workers_detected=14,
            compliant_workers_count=12,
            non_compliant_workers_count=2,
            compliance_rate=85.7,
            kacamata_violations=1,
            glove_violations=1,
            camera_code="CAM-01",
            location="Drill Floor",
            created_at=dt_1042,
        )
        db.add(s_1042)
        await db.flush()

        # 4. Buat 14 WorkerRecords pada sesi 10:42
        personnel_data = [
            {"id": "W-101", "track_id": 101, "role": "Driller", "loc": "Drill Floor", "cam": "CAM-01", "missing": [], "conf": 0.95},
            {"id": "W-102", "track_id": 102, "role": "Derrickman", "loc": "Catwalk", "cam": "CAM-03", "missing": [], "conf": 0.93},
            {"id": "W-103", "track_id": 103, "role": "Floorman", "loc": "Pipe Rack", "cam": "CAM-03", "missing": [], "conf": 0.89},
            {"id": "W-104", "track_id": 104, "role": "Roustabout", "loc": "Drill Floor", "cam": "CAM-01", "missing": ["kacamata"], "conf": 0.91},
            {"id": "W-105", "track_id": 105, "role": "Floorman", "loc": "Drill Floor", "cam": "CAM-01", "missing": [], "conf": 0.94},
            {"id": "W-106", "track_id": 106, "role": "Motorman", "loc": "Mud Pump", "cam": "CAM-02", "missing": [], "conf": 0.92},
            {"id": "W-107", "track_id": 107, "role": "Roustabout", "loc": "Catwalk", "cam": "CAM-03", "missing": [], "conf": 0.90},
            {"id": "W-108", "track_id": 108, "role": "Floorman", "loc": "Mud Pump", "cam": "CAM-02", "missing": ["glove"], "conf": 0.88},
            {"id": "W-109", "track_id": 109, "role": "Roughneck", "loc": "Catwalk", "cam": "CAM-03", "missing": [], "conf": 0.94},
            {"id": "W-110", "track_id": 110, "role": "Mud Engineer", "loc": "Mud Pump", "cam": "CAM-02", "missing": [], "conf": 0.93},
            {"id": "W-111", "track_id": 111, "role": "Crane Operator", "loc": "Pipe Rack", "cam": "CAM-03", "missing": [], "conf": 0.95},
            {"id": "W-112", "track_id": 112, "role": "Roughneck", "loc": "Substructure", "cam": "CAM-04", "missing": [], "conf": 0.87},
            {"id": "W-113", "track_id": 113, "role": "Welder", "loc": "Substructure", "cam": "CAM-04", "missing": [], "conf": 0.91},
            {"id": "W-114", "track_id": 114, "role": "Toolpusher", "loc": "Drill Floor", "cam": "CAM-01", "missing": [], "conf": 0.96},
        ]

        worker_records_map = {}
        for p in personnel_data:
            missing = p["missing"]
            is_comp = len(missing) == 0
            wr = WorkerRecord(
                session_id=s_1042.id,
                frame_idx=0,
                track_id=p["track_id"],
                worker_id=p["id"],
                camera_code=p["cam"],
                location=p["loc"],
                person_conf=p["conf"],
                helm_worn="helm" not in missing,
                kacamata_worn="kacamata" not in missing,
                glove_worn="glove" not in missing,
                sepatu_worn="sepatu" not in missing,
                is_compliant=is_comp,
                status="open" if not is_comp else None,
                missing_apd=json.dumps(missing) if not is_comp else None,
                detected_at=dt_1042,
            )
            db.add(wr)
            await db.flush()
            worker_records_map[p["id"]] = wr

        wr_map_0700 = {}
        wr_map_0900 = {}
        # Buat records untuk sesi-sesi sebelumnya agar data histori lengkap
        for p in personnel_data:
            # Sesi 07:00 (W-109 missing kacamata)
            m_0700 = ["kacamata"] if p["id"] == "W-109" else []
            wr_0700 = WorkerRecord(
                session_id=s_0700.id,
                frame_idx=0,
                track_id=p["track_id"],
                worker_id=p["id"],
                camera_code=p["cam"],
                location=p["loc"],
                person_conf=p["conf"],
                helm_worn="helm" not in m_0700,
                kacamata_worn="kacamata" not in m_0700,
                glove_worn="glove" not in m_0700,
                sepatu_worn="sepatu" not in m_0700,
                is_compliant=len(m_0700) == 0,
                status="handled" if p["id"] == "W-109" else None,
                missing_apd=json.dumps(m_0700) if m_0700 else None,
                detected_at=dt_0700,
            )
            db.add(wr_0700)
            wr_map_0700[p["id"]] = wr_0700

            # Sesi 08:00 (semua patuh)
            wr_0800 = WorkerRecord(
                session_id=s_0800.id,
                frame_idx=0,
                track_id=p["track_id"],
                worker_id=p["id"],
                camera_code=p["cam"],
                location=p["loc"],
                person_conf=p["conf"],
                helm_worn=True,
                kacamata_worn=True,
                glove_worn=True,
                sepatu_worn=True,
                is_compliant=True,
                detected_at=dt_0800,
            )
            db.add(wr_0800)

            # Sesi 09:00 (W-103 missing glove)
            m_0900 = ["glove"] if p["id"] == "W-103" else []
            wr_0900 = WorkerRecord(
                session_id=s_0900.id,
                frame_idx=0,
                track_id=p["track_id"],
                worker_id=p["id"],
                camera_code=p["cam"],
                location=p["loc"],
                person_conf=p["conf"],
                helm_worn="helm" not in m_0900,
                kacamata_worn="kacamata" not in m_0900,
                glove_worn="glove" not in m_0900,
                sepatu_worn="sepatu" not in m_0900,
                is_compliant=len(m_0900) == 0,
                status="handled" if p["id"] == "W-103" else None,
                missing_apd=json.dumps(m_0900) if m_0900 else None,
                detected_at=dt_0900,
            )
            db.add(wr_0900)
            wr_map_0900[p["id"]] = wr_0900

            # Sesi 10:00 (semua patuh)
            wr_1000 = WorkerRecord(
                session_id=s_1000.id,
                frame_idx=0,
                track_id=p["track_id"],
                worker_id=p["id"],
                camera_code=p["cam"],
                location=p["loc"],
                person_conf=p["conf"],
                helm_worn=True,
                kacamata_worn=True,
                glove_worn=True,
                sepatu_worn=True,
                is_compliant=True,
                detected_at=dt_1000,
            )
            db.add(wr_1000)
        await db.flush()

        # 5. Buat 4 records Pelanggaran sesuai spesifikasi
        # (1) 10:38:52 W-104 kacamata open conf 0.91
        v_104 = Violation(
            worker_record_id=worker_records_map["W-104"].id,
            session_id=s_1042.id,
            worker_id="W-104",
            worker_role="Roustabout",
            camera_code="CAM-01",
            location="Drill Floor",
            missing_apd=json.dumps(["kacamata"]),
            status="open",
            confidence=0.91,
            snapshot_path="outputs/V-104.jpg",
            detected_at=datetime(2026, 11, 4, 3, 38, 52, tzinfo=timezone.utc),
        )
        db.add(v_104)

        # (2) 10:31:07 W-108 glove open conf 0.88
        v_108 = Violation(
            worker_record_id=worker_records_map["W-108"].id,
            session_id=s_1042.id,
            worker_id="W-108",
            worker_role="Floorman",
            camera_code="CAM-02",
            location="Mud Pump",
            missing_apd=json.dumps(["glove"]),
            status="open",
            confidence=0.88,
            snapshot_path="outputs/V-108.jpg",
            detected_at=datetime(2026, 11, 4, 3, 31, 7, tzinfo=timezone.utc),
        )
        db.add(v_108)

        # (3) 08:58:40 W-103 glove handled 09:13 conf 0.89
        v_103 = Violation(
            worker_record_id=wr_map_0900["W-103"].id,
            session_id=s_0900.id,
            worker_id="W-103",
            worker_role="Floorman",
            camera_code="CAM-03",
            location="Pipe Rack",
            missing_apd=json.dumps(["glove"]),
            status="handled",
            confidence=0.89,
            snapshot_path="outputs/V-103.jpg",
            detected_at=datetime(2026, 11, 4, 1, 58, 40, tzinfo=timezone.utc),
            handled_at=datetime(2026, 11, 4, 2, 13, 0, tzinfo=timezone.utc),
            handled_by="Akmal Manggala",
            handling_note="Diberikan sarung tangan cadangan oleh Toolpusher.",
        )
        db.add(v_103)

        # (4) 07:00:12 W-109 kacamata handled 07:09 conf 0.94
        v_109 = Violation(
            worker_record_id=wr_map_0700["W-109"].id,
            session_id=s_0700.id,
            worker_id="W-109",
            worker_role="Roughneck",
            camera_code="CAM-03",
            location="Catwalk",
            missing_apd=json.dumps(["kacamata"]),
            status="handled",
            confidence=0.94,
            snapshot_path="outputs/V-109.jpg",
            detected_at=datetime(2026, 11, 4, 0, 0, 12, tzinfo=timezone.utc),
            handled_at=datetime(2026, 11, 4, 0, 9, 12, tzinfo=timezone.utc),
            handled_by="Akmal Manggala",
            handling_note="Petugas mengambil safety glasses dari loker K3.",
        )
        db.add(v_109)

        await db.commit()
        print("Seed demo berhasil diselesaikan dengan sukses!")


if __name__ == "__main__":
    asyncio.run(seed())
