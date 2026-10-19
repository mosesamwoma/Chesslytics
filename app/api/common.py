from __future__ import annotations

from fastapi import HTTPException, UploadFile

from app import settings

CHUNK_BYTES = 1024 * 256


async def read_upload(file: UploadFile) -> str:
    limit = settings.max_upload_bytes()
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(CHUNK_BYTES)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"the uploaded file exceeds {limit // (1024 * 1024)} MiB",
            )
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="the uploaded file is empty")
    return b"".join(chunks).decode("utf-8", errors="replace").replace("\x00", "")
