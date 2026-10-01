# Spesifikasi & Pembagian Tugas — api-apd

> Repo: `api-apd` | Backend Gateway Sistem Deteksi APD PDU Migas  
> Lead / QA: **[nama kamu]**  
> Tanggal: Oktober 2026

---

## Arsitektur Sistem

```
┌─────────────┐     HTTP     ┌───────────────┐     HTTP     ┌──────────────┐
│   fe-apd    │ ──────────▶  │   api-apd     │ ──────────▶  │   ml-apd     │
│  (Frontend) │              │  :8000        │              │  :8001       │
│             │ ◀──────────  │  (Gateway)    │ ◀──────────  │  (Inference) │
└─────────────┘              └───────────────┘              └──────────────┘
                                    │
                                    ▼
                              ┌──────────┐
                              │ SQLite   │
                              │ (DB)     │
                              └──────────┘
```

**api-apd** bertugas sebagai:
- Pintu masuk semua request dari FE
- Autentikasi & otorisasi (JWT)
- Persistensi data (sesi deteksi, worker records, settings)
- Forward request inferensi ke **ml-apd**, simpan hasilnya ke DB
- Sajikan dashboard, statistik, dan export CSV

**ml-apd** adalah pure inference service. Tidak ada auth, tidak ada DB. api-apd saja yang boleh memanggilnya.

---

## Branch Strategy

| Branch | Tujuan |
|---|---|
| `main` | Production-ready. Hanya Lead yang merge ke sini. |
| `develop` | Integration branch. Semua feature branch di-merge ke sini dulu. |
| `feature/auth` | Modul auth — dikerjakan Fadli |
| `feature/detection` | Modul detection gateway — dikerjakan Ghathfan |
| `feature/dashboard` | Modul dashboard + settings — dikerjakan Athaya |

**Alur kerja:**
```
feature/xxx  →  develop  →  main
               (Lead QA)   (Lead merge)
```

Pull Request wajib ke branch `develop`. Lead yang review dan merge.

---

## Struktur Folder Target

```
api-apd/
├── app/
│   ├── main.py               ← Lead (setup awal, register semua router)
│   ├── config.py             ← Lead
│   ├── database.py           ← Lead
│   ├── core/
│   │   ├── security.py       ← Fadli (feature/auth)
│   │   └── deps.py           ← Fadli (feature/auth)
│   ├── models/
│   │   ├── user.py           ← Fadli (feature/auth)
│   │   ├── session.py        ← Ghathfan (feature/detection)
│   │   ├── worker.py         ← Ghathfan (feature/detection)
│   │   └── system_settings.py ← Athaya (feature/dashboard)
│   ├── schemas/
│   │   ├── auth.py           ← Fadli (feature/auth)
│   │   ├── detection.py      ← Ghathfan (feature/detection)
│   │   ├── dashboard.py      ← Athaya (feature/dashboard)
│   │   └── settings.py       ← Athaya (feature/dashboard)
│   ├── routers/
│   │   ├── auth.py           ← Fadli (feature/auth)
│   │   ├── detection.py      ← Ghathfan (feature/detection)
│   │   ├── dashboard.py      ← Athaya (feature/dashboard)
│   │   └── settings.py       ← Athaya (feature/dashboard)
│   └── services/
│       └── ml_client.py      ← Ghathfan (feature/detection)
├── requirements.txt          ← Lead
├── .gitignore
├── README.md
└── spec.md                   ← Dokumen ini
```

---

## Pembagian Tugas Detail

---

### Fadli Sutaji Muidita — `feature/auth`

**Tanggung jawab:** Modul autentikasi lengkap.

#### File yang dikerjakan

**`app/core/security.py`**
- Fungsi `get_password_hash(password)` → pakai bcrypt
- Fungsi `verify_password(plain, hashed)` → verifikasi bcrypt
- Fungsi `create_access_token(data, expires_delta)` → JWT encode
- Fungsi `decode_token(token)` → JWT decode

**`app/core/deps.py`**
- `get_current_user(token, db)` → validasi JWT, return User object
- `get_current_user_optional(token, db)` → sama tapi tidak raise error jika token kosong (untuk endpoint yang auth-nya opsional)

**`app/models/user.py`** — ORM model tabel `users`
```
id, username, email, full_name, hashed_password, role, is_active, created_at
```

**`app/schemas/auth.py`** — Pydantic schemas
- `UserRegister` → input register
- `UserLogin` → input login (username + password)
- `UserResponse` → output data user (tanpa password)
- `Token` → output login berisi access_token + user

**`app/routers/auth.py`** — Router prefix `/auth`

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `POST` | `/auth/register` | Tidak | Daftar akun baru. Role: `admin` atau `supervisor` |
| `POST` | `/auth/login` | Tidak | Login, balik JWT token |
| `POST` | `/auth/token` | Tidak | Sama seperti login tapi format OAuth2 (untuk Swagger UI) |
| `GET` | `/auth/me` | Ya | Return profil user yang sedang login |

#### Catatan teknis
- Gunakan `python-jose[cryptography]` untuk JWT
- Gunakan `passlib[bcrypt]` untuk hashing
- Role yang valid: `"admin"` dan `"supervisor"`
- Token expire: 24 jam (ambil dari `settings.ACCESS_TOKEN_EXPIRE_MINUTES`)

---

### Ghathfan Fadli Zam Autady — `feature/detection`

**Tanggung jawab:** Detection gateway (forward ke ml-apd) + persistensi session ke DB.

#### File yang dikerjakan

**`app/services/ml_client.py`** — HTTP client ke ml-apd
- `call_ml_image(file_bytes, filename, content_type, params)` → POST ke `ml-apd/infer/image`
- `call_ml_video(file_bytes, filename, content_type, params)` → POST ke `ml-apd/infer/video`
- `call_ml_stream_frame(payload)` → POST ke `ml-apd/infer/stream-frame`
- Gunakan `httpx.AsyncClient`
- Timeout: image=60s, video=300s, stream=10s
- Jika ml-apd tidak bisa diakses → raise HTTP 503

**`app/models/session.py`** — ORM model tabel `detection_sessions`
```
id, session_code, source_type, filename, annotated_output_path,
total_frames, total_workers_detected, compliant_workers_count,
non_compliant_workers_count, compliance_rate,
helm_violations, glove_violations, sepatu_violations, kacamata_violations,
summary_notes, created_at
```

**`app/models/worker.py`** — ORM model tabel `worker_records`
```
id, session_id (FK), frame_idx, track_id,
bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_conf,
helm_worn, glove_worn, sepatu_worn, kacamata_worn,
is_compliant, detection_details (JSON text), detected_at
```

**`app/schemas/detection.py`** — Pydantic schemas
- `ImageDetectRequest` (query params yang akan diteruskan ke ml-apd)
- `VideoDetectRequest`
- `StreamFrameRequest` (body JSON)
- `ImageDetectionResponse` (response ke FE, sudah include session_id dari DB)
- `VideoDetectionResponse`
- `StreamFrameResponse`
- `SessionListItem`, `SessionDetailResponse`

**`app/routers/detection.py`** — Router prefix `/detect`

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `POST` | `/detect/image` | Opsional | Upload gambar → forward ke ml-apd → simpan session ke DB → return hasil |
| `POST` | `/detect/video` | Opsional | Upload video → forward ke ml-apd → simpan session → return hasil |
| `POST` | `/detect/stream-frame` | Tidak | Forward frame base64 ke ml-apd → return hasil langsung (tidak simpan ke DB) |
| `GET` | `/detect/sessions` | Ya | List histori sesi. Query params: `skip`, `limit`, `source_type` |
| `GET` | `/detect/sessions/{session_id}` | Ya | Detail sesi + worker records |
| `DELETE` | `/detect/sessions/{session_id}` | Ya | Hapus sesi |

#### Catatan teknis
- Setelah dapat respons dari ml-apd, buat record `DetectionSession` di DB, lalu loop workers untuk buat `WorkerRecord`
- `stream-frame` **tidak perlu** simpan ke DB (terlalu sering dipanggil, simpan hanya saat session selesai)
- Semua config threshold (helm_conf, glove_conf, dll) diambil dari tabel `system_settings` di DB, lalu dikirim sebagai query params ke ml-apd

---

### Athaya Ichsan Ramadhan — `feature/dashboard`

**Tanggung jawab:** Dashboard statistik kepatuhan + konfigurasi sistem (ROI, threshold).

#### File yang dikerjakan

**`app/models/system_settings.py`** — ORM model tabel `system_settings`
```
id (always 1), roi_active, roi_x1, roi_y1, roi_x2, roi_y2,
overlap_threshold, person_conf, helm_conf, glove_conf, sepatu_conf, kacamata_conf,
enable_head_zoom, head_crop_ratio, head_zoom_conf,
enable_temporal_persistence, temporal_memory_frames,
updated_at
```

**`app/schemas/dashboard.py`** — Pydantic schemas
- `DashboardSummary` → total sesi, total pekerja, compliance rate, violations by APD
- `ComplianceTrendPoint` → per-tanggal: total_workers, compliant, violations, rate
- `APDViolationStat` → per-APD: violation_count, compliance_percentage

**`app/schemas/settings.py`** — Pydantic schemas
- `ROIConfig` → active, x1, y1, x2, y2
- `ThresholdsConfig` → semua threshold
- `SettingsResponse` → gabungan ROI + thresholds + updated_at
- `SettingsUpdateRequest` → partial update (ROI dan/atau thresholds)

**`app/routers/dashboard.py`** — Router prefix `/dashboard`

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/dashboard/summary` | Ya | Statistik overall. Query params: `start_date`, `end_date` |
| `GET` | `/dashboard/compliance-trends` | Ya | Trend harian. Query param: `days` (default 7, max 90) |
| `GET` | `/dashboard/worker-records` | Ya | Filter worker records. Params: `is_compliant`, `missing_apd`, `session_id`, `limit`, `offset` |
| `GET` | `/dashboard/export` | Ya | Download CSV laporan kepatuhan |

**`app/routers/settings.py`** — Router prefix `/settings`

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/settings` | Tidak | Ambil konfigurasi aktif (ROI + thresholds) |
| `PUT` | `/settings` | Opsional | Update konfigurasi. Perubahan langsung efek ke deteksi berikutnya |

#### Catatan teknis
- `system_settings` hanya punya 1 row dengan `id=1`. Kalau belum ada, buat dengan nilai default
- Export CSV gunakan `csv` module dari stdlib, return sebagai `Response` dengan `media_type="text/csv"`
- Trend di-group per tanggal (`YYYY-MM-DD`) dari `created_at` sesi

---

## Kontrak API antara api-apd dan ml-apd

Ghathfan perlu tahu ini untuk buat `ml_client.py`.

### POST `ml-apd/infer/image`
```
Form: file (multipart)
Query params:
  overlap_threshold, enable_head_zoom,
  helm_conf, glove_conf, sepatu_conf, kacamata_conf, person_conf,
  roi_active, roi_x1, roi_y1, roi_x2, roi_y2

Response JSON:
{
  "session_code": "IMG-XXXXXXXX",
  "total_workers": 3,
  "compliant_workers_count": 2,
  "non_compliant_workers_count": 1,
  "compliance_rate": 66.67,
  "workers": [...],
  "all_detected_apds": [...],
  "annotated_image_url": "/outputs/IMG-xxx_annotated.jpg",
  "annotated_image_base64": "data:image/jpeg;base64,...",
  "inference_time_ms": 120.5,
  "two_stage_zoom_applied": true
}
```

### POST `ml-apd/infer/video`
```
Form: file (multipart)
Query params: sample_stride, overlap_threshold, helm_conf, glove_conf, sepatu_conf, kacamata_conf, person_conf

Response JSON:
{
  "session_code": "VID-XXXXXXXX",
  "total_frames_processed": 100,
  "total_unique_workers": 4,
  "compliant_workers_count": 3,
  "non_compliant_workers_count": 1,
  "overall_compliance_rate": 75.0,
  "helm_violations": 1,
  "glove_violations": 0,
  "sepatu_violations": 0,
  "kacamata_violations": 1,
  "annotated_video_url": "/outputs/VID-xxx_annotated.mp4",
  "annotated_sample_frames": [...],
  "processing_time_sec": 12.4,
  "workers_summary": [...],
  "status": "completed"
}
```

### POST `ml-apd/infer/stream-frame`
```
Body JSON:
{
  "client_id": "client_abc",
  "session_code": "STREAM-123",
  "frame_base64": "data:image/jpeg;base64,..."
}

Response JSON:
{
  "client_id": "client_abc",
  "session_code": "STREAM-123",
  "frame_idx": 42,
  "total_workers": 2,
  "compliant_workers": 1,
  "non_compliant_workers": 1,
  "workers": [...],
  "annotated_frame_base64": "data:image/jpeg;base64,...",
  "fps": 12.3
}
```

---

## Requirements (api-apd)

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.7.0
python-multipart>=0.0.9
sqlalchemy>=2.0.0
aiosqlite>=0.20.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
httpx>=0.27.0
```

---

## Checklist Sebelum PR ke `develop`

- [ ] Semua endpoint berjalan tanpa error di local
- [ ] Tidak ada import yang belum dipakai
- [ ] Tidak ada hardcoded secret atau password
- [ ] Response model sudah sesuai schema (tidak ada field yang hilang)
- [ ] Error handling: input tidak valid → 400, tidak ditemukan → 404, tidak authorized → 401/403
- [ ] Sudah test manual via Swagger UI (`/docs`)
