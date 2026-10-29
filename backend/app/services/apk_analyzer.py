"""APK metadata extraction via Android SDK apkanalyzer, with androguard fallback.

Ported from manual_android_accessibility_scan.py (locate_apkanalyzer /
read_apk_metadata), adapted to resolve tools through app.config.

apkanalyzer needs aapt from the SDK build-tools package; when build-tools is
not installed (or any apkanalyzer call fails) we fall back to androguard,
which parses the binary AndroidManifest.xml in pure Python.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from ..adb import run_command
from ..config import get_settings


def locate_apkanalyzer() -> str | None:
    path = shutil.which("apkanalyzer")
    if path:
        return path

    candidates: list[Path] = []
    sdk = Path(get_settings().ANDROID_SDK_ROOT)
    candidates.extend((sdk / "cmdline-tools").glob("*/bin/apkanalyzer*"))
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return None
    # Prefer 'latest' when available, otherwise the lexicographically newest folder.
    existing.sort(key=lambda p: ("latest" in p.parts, str(p)), reverse=True)
    return str(existing[0])


def _apkanalyzer_value(exe: str, subject: str, verb: str, apk: Path) -> str:
    proc = run_command([exe, subject, verb, str(apk)], timeout=45)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"apkanalyzer {subject} {verb} failed: {detail}")
    return proc.stdout.strip()


def sha256_of(apk: Path) -> str:
    digest = hashlib.sha256()
    with apk.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_apk_metadata(apk: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "file_name": apk.name,
        "file_size_bytes": apk.stat().st_size,
        "sha256": sha256_of(apk),
        "application_id": None,
        "version_name": None,
        "version_code": None,
        "min_sdk": None,
        "target_sdk": None,
        "permissions": [],
        "apkanalyzer_available": False,
    }

    analyzer = locate_apkanalyzer()
    if not analyzer:
        return metadata

    metadata["apkanalyzer_available"] = True
    fields = {
        "application_id": ("manifest", "application-id"),
        "version_name": ("manifest", "version-name"),
        "version_code": ("manifest", "version-code"),
        "min_sdk": ("manifest", "min-sdk"),
        "target_sdk": ("manifest", "target-sdk"),
    }
    for key, (subject, verb) in fields.items():
        try:
            metadata[key] = _apkanalyzer_value(analyzer, subject, verb, apk) or None
        except Exception:
            # Keep analysis possible even if a single field cannot be read.
            pass

    try:
        raw = _apkanalyzer_value(analyzer, "manifest", "permissions", apk)
        metadata["permissions"] = [line.strip() for line in raw.splitlines() if line.strip()]
    except Exception:
        pass

    if metadata["application_id"] is None:
        _fill_from_androguard(apk, metadata)

    return metadata


def _fill_from_androguard(apk: Path, metadata: dict[str, Any]) -> None:
    """Fallback parser for when apkanalyzer cannot run (e.g. no build-tools)."""
    try:
        from loguru import logger

        logger.remove()  # androguard is extremely chatty on stderr otherwise
    except ImportError:
        pass
    try:
        from androguard.core.apk import APK
    except ImportError:
        return
    try:
        parsed = APK(str(apk))
        metadata["application_id"] = metadata["application_id"] or parsed.get_package()
        metadata["version_name"] = metadata["version_name"] or parsed.get_androidversion_name()
        code = parsed.get_androidversion_code()
        metadata["version_code"] = metadata["version_code"] or (str(code) if code else None)
        metadata["min_sdk"] = metadata["min_sdk"] or parsed.get_min_sdk_version()
        metadata["target_sdk"] = metadata["target_sdk"] or parsed.get_target_sdk_version()
        if not metadata["permissions"]:
            metadata["permissions"] = list(parsed.get_permissions())
    except Exception:
        pass
