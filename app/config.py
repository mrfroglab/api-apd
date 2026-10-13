import os


class Settings:
    PROJECT_NAME: str = "api-apd"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-pdu-migas-apd-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))  # 24 jam
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./apd_gateway.db")
    CORS_ORIGINS: list[str] = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",")]
    ML_SERVICE_URL: str = os.getenv("ML_SERVICE_URL", "http://localhost:8001")


settings = Settings()
