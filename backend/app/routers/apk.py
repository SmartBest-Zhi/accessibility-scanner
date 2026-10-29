"""APK upload + metadata analysis."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from ..config import get_settings
from ..services import apk_analyzer

router = APIRouter(prefix="/apk", tags=["apk"])


def _apk_dir(apk_id: str) -> Path:
    return get_settings().uploads_dir / apk_id


def _find_apk(apk_id: str) -> Path:
    directory = _apk_dir(apk_id)
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown apk_id: {apk_id}")
    apks = list(directory.glob("*.apk"))
    if not apks:
        raise HTTPException(status_code=404, detail=f"No APK stored for id: {apk_id}")
    return apks[0]


@router.post("")
async def upload_apk(file: UploadFile) -> dict:
    if not file.filename or not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="仅支持上传 .apk 文件")

    # Stream to a temp file while hashing, then dedupe by sha256 prefix.
    tmp_dir = get_settings().uploads_dir
    tmp_path = tmp_dir / f".uploading-{file.filename}"
    digest = hashlib.sha256()
    with tmp_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)

    apk_id = digest.hexdigest()[:12]
    final_dir = _apk_dir(apk_id)
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / file.filename
    tmp_path.replace(final_path)

    metadata = apk_analyzer.read_apk_metadata(final_path)
    return {"apk_id": apk_id, "metadata": metadata}


def load_apk(apk_id: str) -> tuple[Path, dict]:
    """Used by the session router when starting a session."""
    apk_path = _find_apk(apk_id)
    return apk_path, apk_analyzer.read_apk_metadata(apk_path)
