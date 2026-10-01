# api-apd

API Gateway untuk Sistem Deteksi APD PDU Migas.

Handles auth, session persistence, dashboard, dan settings.
Inference request diteruskan ke service `ml-apd` (port 8001).

## Stack
- Python 3.10+
- FastAPI + Uvicorn
- SQLAlchemy async + aiosqlite
- JWT (python-jose) + bcrypt (passlib)
- httpx (untuk call ml-apd)

## Cara Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Environment Variables
| Variable | Default | Keterangan |
|---|---|---|
| `ML_SERVICE_URL` | `http://localhost:8001` | URL ml-apd inference service |
| `SECRET_KEY` | *(wajib diganti di prod)* | JWT signing key |
| `DATABASE_URL` | `sqlite+aiosqlite:///apd_gateway.db` | Database connection |
| `CORS_ORIGINS` | `*` | Allowed origins |

## Lihat spec.md untuk detail pembagian tugas per anggota.
