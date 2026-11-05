from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, run_lightweight_migrations
from app.routers.auth import router as auth_router
from app.routers.cameras import router as cameras_router
from app.routers.dashboard import router as dashboard_router
from app.routers.detection import router as detection_router
from app.routers.settings import router as settings_router
from app.routers.violations import router as violations_router
from app.routers.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Buat tabel di database jika belum ada
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_lightweight_migrations(conn)
    yield


app = FastAPI(
    title="api-apd Gateway",
    description="Backend API Gateway untuk Sistem Deteksi APD PDU Migas",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(cameras_router)
app.include_router(violations_router)
app.include_router(detection_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(ws_router)


@app.get("/", tags=["health"])
async def root():
    return {
        "status": "ok",
        "service": "api-apd",
        "message": "API Gateway Sistem Deteksi APD PDU Migas is running"
    }

import os
if os.getenv("PMLD_ENABLE_TEST_RESET") == "1":
    @app.post("/__test__/reset", tags=["test"])
    async def test_reset():
        from app.database import AsyncSessionLocal
        from app.models.violation import Violation
        from app.models.worker import WorkerRecord
        from app.models.session import DetectionSession
        from app.models.camera import Camera, CameraROI
        from app.models.system_settings import SystemSettings
        from sqlalchemy import delete
        from scripts.seed_demo import seed

        async with AsyncSessionLocal() as db:
            await db.execute(delete(Violation))
            await db.execute(delete(WorkerRecord))
            await db.execute(delete(DetectionSession))
            await db.execute(delete(CameraROI))
            await db.execute(delete(Camera))
            await db.execute(delete(SystemSettings))
            await db.commit()

        await seed()
        return {"status": "ok", "message": "Database reset and reseeded successfully"}
