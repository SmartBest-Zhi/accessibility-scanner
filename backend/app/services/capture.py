"""Pure-adb screen capture: screenshots, UI hierarchy XML, device info."""

from __future__ import annotations

import re
import struct
import time
from pathlib import Path

from ..adb import adb_exec_out_bytes, adb_shell_text, run_command, adb_cmd

_DENSITY_RE = re.compile(r"density\s*:\s*(\d+)", re.IGNORECASE)
_SIZE_RE = re.compile(r"(?:Override|Physical) size:\s*(\d+)x(\d+)")
_FOCUS_RE = re.compile(r"mCurrentFocus=\S+\s+\S+\s+([\w.]+)/([\w.$]+)")


def capture_screenshot(udid: str, dest: Path) -> None:
    """Save a PNG screenshot via exec-out (binary-safe)."""
    data = adb_exec_out_bytes(udid, "screencap", "-p", timeout=30)
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError("screencap did not return PNG data")
    dest.write_bytes(data)


def png_size(path: Path) -> tuple[int, int] | None:
    """Read (width, height) from the PNG IHDR without decoding the image."""
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        width, height = struct.unpack(">II", header[16:24])
        return width, height
    except OSError:
        return None


def dump_ui_xml(udid: str, retries: int = 1) -> str:
    """Dump the current UI hierarchy via uiautomator and return the XML text.

    `uiautomator dump` intermittently fails during screen transitions
    ('null root node'); retry once after a short wait.
    """
    remote = "/sdcard/a11y_scan_dump.xml"
    last_error = "unknown error"
    for attempt in range(retries + 1):
        proc = adb_shell_text(udid, "uiautomator", "dump", remote, timeout=30)
        combined = proc.stdout + proc.stderr
        if proc.returncode == 0 and "null" not in combined.lower():
            data = adb_exec_out_bytes(udid, "cat", remote, timeout=15)
            text = data.decode("utf-8", errors="replace")
            if text.strip().startswith("<"):
                return text
            last_error = "dumped file was empty or not XML"
        else:
            last_error = combined.strip() or f"exit code {proc.returncode}"
        if attempt < retries:
            time.sleep(1)
    raise RuntimeError(f"uiautomator dump failed: {last_error}")


def current_focus(udid: str) -> tuple[str | None, str | None]:
    """Return (package, activity) of the focused window."""
    proc = run_command(adb_cmd(udid, "shell", "dumpsys", "window"), timeout=15)
    if proc.returncode != 0:
        return None, None
    for line in proc.stdout.splitlines():
        if "mCurrentFocus" in line:
            match = _FOCUS_RE.search(line)
            if match:
                return match.group(1), match.group(2)
    return None, None


def read_density_dpi(udid: str) -> int | None:
    proc = adb_shell_text(udid, "wm", "density", timeout=10)
    if proc.returncode != 0:
        return None
    matches = _DENSITY_RE.findall(proc.stdout)
    if not matches:
        return None
    try:
        # Prefer the override (last match) — it reflects the active display setting.
        return int(matches[-1])
    except ValueError:
        return None


def read_screen_size(udid: str) -> list[int] | None:
    """Return [width, height] in px from `wm size` (override preferred)."""
    proc = adb_shell_text(udid, "wm", "size", timeout=10)
    if proc.returncode != 0:
        return None
    match = _SIZE_RE.search(proc.stdout)
    return [int(match.group(1)), int(match.group(2))] if match else None


def read_api_level(udid: str) -> str | None:
    proc = adb_shell_text(udid, "getprop", "ro.build.version.sdk", timeout=10)
    return proc.stdout.strip() if proc.returncode == 0 else None


def get_font_scale(udid: str) -> float:
    proc = adb_shell_text(udid, "settings", "get", "system", "font_scale", timeout=10)
    try:
        return float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return 1.0


def set_font_scale(udid: str, value: float) -> None:
    proc = adb_shell_text(udid, "settings", "put", "system", "font_scale", str(value), timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to set font_scale={value}: {proc.stderr.strip()}")
