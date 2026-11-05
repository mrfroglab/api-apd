# api-apd

API Gateway untuk Sistem Pemantauan Kepatuhan APD Terintegrasi AI Vision (PT Parama Data Unit - PDU Migas).

Menangani otentikasi JWT, persistensi sesi inspeksi, manajemen kamera, konfigurasi Region of Interest (ROI), alur penanganan insiden pelanggaran K3, telemetri realtime WebSocket, serta pelaporan dan analitik kepatuhan.

Permintaan komputasi inferensi visi komputer YOLO11 diteruskan ke layanan terpisah `ml-apd`.

---

## 🛠️ Stack Teknologi
- Python 3.12 (kompatibel Python 3.10+)
- FastAPI + Uvicorn
- SQLAlchemy 2.0 async + aiosqlite (SQLite)
- Autentikasi JWT (`python-jose[cryptography]`) + bcrypt
- Ekspor Dokumen: ReportLab (PDF) & CSV
- Klien HTTP async: `httpx`
- Realtime: WebSocket in-process connection manager

---

## 🚀 Cara Menjalankan Secara Lokal

### 1. Persiapan Virtual Environment
```bash
# Aktifkan virtual environment
source .venv/bin/activate

# Pasang dependensi
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Konfigurasi Port & Environment Variables
Salin contoh konfigurasi atau gunakan konfigurasi lokal:
```bash
cp .env.example .env
```

Pada mesin workstation ini, gunakan port unik berikut:
- **api-apd**: `PORT=8740`
- **ml-apd**: `ML_SERVICE_URL=http://localhost:8741`
- **CORS_ORIGINS**: `http://localhost:3000`
- **APP_TZ**: `Asia/Jakarta` (default WIB / UTC+7)
- **PMLD_DEMO_NOW**: Opsional titik waktu acuan demo (contoh: `2026-11-04T10:42:18+07:00`)

### 3. Seed Data Demo
Jalankan script seed untuk menginisialisasi 4 kamera rig, 14 pekerja (W-101..W-114), catatan pelanggaran, dan akun demo HSE (bersifat idempotent):
```bash
python -m scripts.seed_demo
```

**Kredensial Dev Demo:**
- **Email / Username**: `hse@pdu.co.id`
- **Password**: `pmld-demo-2026`

### 4. Menjalankan Server
Jalankan skrip eksekusi otomatis:
```bash
./run.sh
```
Skrip `run.sh` telah dilengkapi trap sinyal `SIGINT`, `SIGTERM`, dan `EXIT` untuk menghentikan supervisor Uvicorn dan proses reloader child hingga tuntas.

### 5. Menghentikan Server
- **Foreground**: Tekan `Ctrl+C` pada terminal tempat `run.sh` berjalan.
- **Background / Port Cleanup**: Jika proses Uvicorn menyisakan listener port, jalankan:
```bash
fuser -k "${PORT:-8740}/tcp"
# atau:
kill -9 $(lsof -t -i:"${PORT:-8740}")
```
---

## 📋 Daftar Endpoint API

### 1. Autentikasi
- `POST /auth/register` : Mendaftarkan akun petugas K3 baru.
- `POST /auth/login` : Masuk menggunakan username atau email dan password, menghasilkan Bearer JWT.
- `POST /auth/token` : Login form OAuth2 untuk antarmuka Swagger UI (`/docs`).
- `GET /auth/me` : Profil pengguna yang sedang terotentikasi.

### 2. Manajemen Kamera & ROI
- `GET /cameras` : Daftar seluruh kamera terdaftar beserta status operasional (`online`/`offline`) dan `disconnected_since`.
- `POST /cameras` : Menambahkan unit kamera CCTV baru.
- `GET /cameras/{code}` : Informasi detail kamera berdasarkan kode (contoh: `CAM-01`).
- `PATCH /cameras/{code}` : Memperbarui konfigurasi kamera (nama, lokasi, status, fps, is_active).
- `POST /cameras/{code}/heartbeat` : Mengirim sinyal detak kamera (memperbarui `last_seen_at` dan status `online`).
- `GET /cameras/{code}/rois` : Mengambil daftar Region of Interest (ROI) poligon untuk kamera terkait.
- `PUT /cameras/{code}/rois` : Memperbarui seluruh himpunan poligon ROI per kamera (validasi minimal 3 titik, rentang 0..1).
- `DELETE /cameras/{code}/rois/{roi_id}` : Menghapus satu poligon ROI kamera.

### 3. Pelanggaran K3 & Bukti Snapshot
- `GET /violations` : Daftar log pelanggaran K3 terfilter (`status`, `camera_code`, `apd`, `date_from`, `date_to`, `q`, `limit`, `offset`) dengan total record.
- `GET /violations/{id}` : Detail pelanggaran dan tautan bukti snapshot.
- `POST /violations/{id}/handle` : Menandai pelanggaran telah ditangani K3 beserta catatan investigasi dan nama petugas.
- `POST /violations/{id}/reopen` : Mengembalikan status pelanggaran menjadi terbuka (`open`).
- `GET /violations/{id}/snapshot` : Mengunduh berkas citra bukti pelanggaran K3.

### 4. Deteksi & Riwayat Sesi
- `POST /detect/image` : Unggah citra inspeksi manual, opsional menyertakan `camera_code`.
- `POST /detect/video` : Unggah rekaman video inspeksi, opsional menyertakan `camera_code`.
- `POST /detect/stream-frame` : Teruskan frame base64 CCTV ke layanan visi komputer tanpa I/O disk.
- `GET /detect/sessions` : Daftar riwayat sesi inspeksi.
- `GET /detect/sessions/{session_id}` : Detail sesi dan catatan personil.
- `DELETE /detect/sessions/{session_id}` : Menghapus riwayat sesi.

### 5. Dasbor Analitik & Ekspor
- `GET /dashboard/summary` : Ringkasan KPI kepatuhan K3 berbasis snapshot terbaru per personil unik dalam rentang tanggal/jam (monitored_workers, full_apd_workers, violating_workers, per_apd).
- `GET /dashboard/compliance-trends` : Tren kepatuhan per jam (`granularity=hour`) atau harian (`granularity=day`).
- `GET /dashboard/worker-records` : Catatan deteksi individual pekerja.
- `GET /dashboard/export` : Mengunduh laporan kepatuhan resmi dalam format CSV atau PDF (`format=csv|pdf`).

### 6. Pengaturan Sistem (Settings)
- `GET /settings` : Konfigurasi global ambang batas model, ROI global, `sampling_fps`, `alarm_delay_s`, dan `iou_threshold`.
- `PUT /settings` : Memperbarui konfigurasi sistem secara parsial.

### 7. Telemetri Realtime (WebSocket)
- `WS /ws/live?token=<jwt>&camera_code=<opt>` : Jalur koneksi realtime untuk broadcast event deteksi frame, perubahan status kamera, pelanggaran baru, dan status penanganan insiden.

---

## 🧪 Pengujian Otomatis

Jalankan test suite menggunakan pytest:
```bash
.venv/bin/pytest -q
```
