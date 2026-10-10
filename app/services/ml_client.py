import os

import httpx
from fastapi import HTTPException

# TODO: pindah ke app.config (settings.ML_SERVICE_URL) setelah config.py dari Lead tersedia
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

IMAGE_TIMEOUT = 60.0
VIDEO_TIMEOUT = 300.0
STREAM_TIMEOUT = 10.0


def _clean_params(params: dict | None) -> dict:
    """Buang parameter yang bernilai None supaya tidak ikut terkirim ke ml-apd."""
    return {k: v for k, v in (params or {}).items() if v is not None}


async def _post(
    path: str,
    timeout: float,
    *,
    files: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
) -> dict:
    url = f"{ML_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url, files=files, params=_clean_params(params), json=json
            )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503,
            detail="Layanan inferensi (ml-apd) tidak dapat diakses",
        ) from exc

    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="ml-apd mengembalikan error internal")
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=_extract_detail(response))

    return response.json()


def _extract_detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", "Request ditolak oleh ml-apd"))
    except ValueError:
        return "Request ditolak oleh ml-apd"


async def call_ml_image(
    file_bytes: bytes, filename: str, content_type: str, params: dict | None = None
) -> dict:
    files = {"file": (filename, file_bytes, content_type)}
    return await _post("/infer/image", IMAGE_TIMEOUT, files=files, params=params)


async def call_ml_video(
    file_bytes: bytes, filename: str, content_type: str, params: dict | None = None
) -> dict:
    files = {"file": (filename, file_bytes, content_type)}
    return await _post("/infer/video", VIDEO_TIMEOUT, files=files, params=params)


async def call_ml_stream_frame(payload: dict) -> dict:
    return await _post("/infer/stream-frame", STREAM_TIMEOUT, json=payload)