"""AVD lifecycle: list, cold start, boot wait, install/launch, kill."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from ..adb import adb_cmd, adb_path, adb_shell_text, emulator_path, run_command
from ..config import get_settings


def list_avds() -> list[str]:
    proc = run_command([emulator_path(), "-list-avds"], timeout=20)
    if proc.returncode != 0:
        raise RuntimeError(f"emulator -list-avds failed: {proc.stderr.strip()}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def adb_devices() -> list[tuple[str, str]]:
    """Return (udid, state) pairs, e.g. ('emulator-5554', 'device')."""
    proc = run_command([adb_path(), "devices"], timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(f"adb devices failed: {proc.stderr.strip()}")
    rows: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    return rows


def online_emulator_udid() -> str | None:
    for udid, state in adb_devices():
        if state == "device" and udid.startswith("emulator-"):
            return udid
    return None


def wait_for_boot(udid: str, timeout_s: int | None = None) -> None:
    timeout_s = timeout_s or get_settings().BOOT_TIMEOUT_S
    deadline = time.time() + timeout_s
    run_command(adb_cmd(udid, "wait-for-device"), timeout=timeout_s)
    while time.time() < deadline:
        proc = adb_shell_text(udid, "getprop", "sys.boot_completed", timeout=10)
        if proc.returncode == 0 and proc.stdout.strip() == "1":
            # Give the launcher and system services a little more time to settle.
            time.sleep(3)
            return
        time.sleep(2)
    raise TimeoutError(f"Android did not finish booting within {timeout_s}s: {udid}")


def cold_start(avd_name: str) -> tuple[str, subprocess.Popen[Any]]:
    """Cold-boot an AVD and return (udid, emulator process)."""
    if udid := online_emulator_udid():
        raise RuntimeError(
            f"An emulator is already online ({udid}). End the current session first."
        )
    proc = subprocess.Popen(
        [emulator_path(), "-avd", avd_name, "-no-snapshot-load"],
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    deadline = time.time() + 180
    while time.time() < deadline:
        if udid := online_emulator_udid():
            wait_for_boot(udid)
            return udid, proc
        if proc.poll() is not None:
            raise RuntimeError("AVD process exited before becoming available through adb.")
        time.sleep(2)
    raise TimeoutError("AVD did not appear in adb devices within 180 seconds.")


def install_apk(udid: str, apk: Path) -> None:
    proc = run_command(adb_cmd(udid, "install", "-r", str(apk)), timeout=300)
    if proc.returncode != 0 or "Success" not in (proc.stdout + proc.stderr):
        raise RuntimeError(f"adb install failed: {(proc.stderr or proc.stdout).strip()}")


def launch_app(udid: str, package: str) -> None:
    """Launch the app's launcher activity via monkey (no activity resolution needed)."""
    proc = adb_shell_text(
        udid, "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1", timeout=20
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to launch {package}: {proc.stderr.strip()}")


def kill_emulator(udid: str | None, proc: subprocess.Popen[Any] | None) -> None:
    """Cleanly kill the emulator; fall back to killing the process tree."""
    if udid:
        try:
            run_command(adb_cmd(udid, "emu", "kill"), timeout=15)
            deadline = time.time() + 30
            while time.time() < deadline:
                if all(u != udid for u, _ in adb_devices()):
                    return
                time.sleep(1)
        except Exception:
            pass
    if proc and proc.poll() is None:
        try:
            # /T takes the qemu child tree; /F is required for the npm/emulator wrappers.
            run_command(["taskkill", "/PID", str(proc.pid), "/T", "/F"], timeout=20)
        except Exception:
            pass
