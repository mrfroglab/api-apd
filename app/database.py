from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def run_lightweight_migrations(conn: AsyncConnection) -> None:
    table_columns = {
        "cameras": [
            ("disconnected_since_at", "DATETIME"),
        ],
        "detection_sessions": [
            ("camera_code", "VARCHAR(50)"),
            ("location", "VARCHAR(100)"),
        ],
        "worker_records": [
            ("worker_id", "VARCHAR(50)"),
            ("camera_code", "VARCHAR(50)"),
            ("location", "VARCHAR(100)"),
            ("status", "VARCHAR(20) DEFAULT 'open'"),
            ("missing_apd", "TEXT"),
            ("handled_at", "DATETIME"),
            ("handled_by", "VARCHAR(150)"),
            ("handling_note", "TEXT"),
        ],
        "system_settings": [
            ("sampling_fps", "INTEGER DEFAULT 5"),
            ("alarm_delay_s", "INTEGER DEFAULT 10"),
            ("iou_threshold", "FLOAT DEFAULT 0.45"),
        ],
    }

    for table, columns in table_columns.items():
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing_cols = {row[1] for row in result.fetchall()}
        if not existing_cols:
            continue
        for col_name, col_type in columns:
            if col_name not in existing_cols:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
