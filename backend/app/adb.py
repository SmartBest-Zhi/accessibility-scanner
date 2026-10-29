"""adb / emulator / apkanalyzer subprocess helpers.

`run_command` is ported verbatim in spirit from manual_android_accessibility_scan.py
(Windows .bat/.cmd tools need shell=True via subprocess.list2cmdline).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import get_settings


def run_command(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a command, accounting for .bat/.cmd tools on Windows."""
    string_args = [str(x) for x in args]
    if _is_batch(string_args[0]):
        return subprocess.run(
            subprocess.list2cmdline(string_args),
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    return subprocess.run(
        string_args,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def run_command_bytes(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    """Raw-stdout variant for binary transfers (adb exec-out screencap, cat of XML).

    Never route binary payloads through `adb shell` + text mode: the PTY and
    Windows CRLF translation corrupt them.
    """
    string_args = [str(x) for x in args]
    return subprocess.run(
        string_args,
        shell=False,
        check=False,
        capture_output=True,
        timeout=timeout,
    )


def _is_batch(exe: str) -> bool:
    import os

    return os.name == "nt" and Path(exe).suffix.lower() in {".bat", ".cmd"}


def resolve_tool(name: str, sdk_relative: str | None = None) -> str:
    """Find a tool on PATH, falling back to a path inside the configured SDK."""
    path = shutil.which(name)
    if path:
        return path
    if sdk_relative:
        import os

        suffix = ".exe" if os.name == "nt" else ""
        candidate = Path(get_settings().ANDROID_SDK_ROOT) / sdk_relative / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(
        f"Cannot find '{name}' on PATH or under ANDROID_SDK_ROOT. "
        "Check the Android SDK installation and backend .env."
    )


def adb_path() -> str:
    return resolve_tool("adb", "platform-tools")


def emulator_path() -> str:
    return resolve_tool("emulator", "emulator")


def adb_cmd(udid: str | None, *args: str) -> list[str]:
    cmd = [adb_path()]
    if udid:
        cmd += ["-s", udid]
    return cmd + [str(a) for a in args]


def adb_shell_text(udid: str, *args: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return run_command(adb_cmd(udid, "shell", *args), timeout=timeout)


def adb_exec_out_bytes(udid: str, *args: str, timeout: int = 30) -> bytes:
    proc = run_command_bytes(adb_cmd(udid, "exec-out", *args), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"adb exec-out {' '.join(args)} failed: "
            f"{proc.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return proc.stdout
