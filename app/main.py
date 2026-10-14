from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers.auth import router as auth_router
from app.routers.detection import router as detection_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Buat tabel di database jika belum ada
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
app.include_router(detection_router)


@app.get("/", tags=["health"])
async def root():
    return {
        "status": "ok",
        "service": "api-apd",
        "message": "API Gateway Sistem Deteksi APD PDU Migas is running"
    }
