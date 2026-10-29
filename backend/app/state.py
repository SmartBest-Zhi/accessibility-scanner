"""In-memory session state. One active session at a time (one AVD)."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import get_settings
from .services import wsscrcpy_manager

ACTIVE_STATUSES = {"starting", "booting", "installing", "launching", "ready", "scanning", "ending"}


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Session:
    session_id: str
    avd_name: str
    apk_id: str
    apk_metadata: dict[str, Any]
    run_dir: Path
    status: str = "starting"
    error: str | None = None
    udid: str | None = None
    started_at: str = field(default_factory=_now_iso)
    ended_at: str | None = None
    device_info: dict[str, Any] = field(default_factory=dict)
    emulator_proc: subprocess.Popen[Any] | None = None
    wsscrcpy_proc: subprocess.Popen[Any] | None = None
    scans: list[dict[str, Any]] = field(default_factory=list)
    log: list[dict[str, str]] = field(default_factory=list)
    current_task: asyncio.Task[Any] | None = field(default=None, repr=False)

    def transition(self, status: str, message: str = "") -> None:
        self.status = status
        self.log.append({"ts": _now_iso(), "status": status, "message": message})
        self.persist()

    def fail(self, message: str) -> None:
        self.error = message
        self.transition("failed", message)

    @property
    def stream_url(self) -> str | None:
        if self.udid and self.wsscrcpy_proc and self.wsscrcpy_proc.poll() is None:
            return wsscrcpy_manager.stream_url(self.udid)
        if self.udid and wsscrcpy_manager.server_is_up():
            return wsscrcpy_manager.stream_url(self.udid)
        return None

    @property
    def finding_count(self) -> int:
        return sum(len(scan.get("findings", [])) for scan in self.scans)

    def persist(self) -> None:
        data = {
            "session_id": self.session_id,
            "status": self.status,
            "error": self.error,
            "avd_name": self.avd_name,
            "udid": self.udid,
            "apk_id": self.apk_id,
            "apk": self.apk_metadata,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "device": self.device_info,
            "scans": self.scans,
            "log": self.log,
        }
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "session.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def summary(self) -> dict[str, Any]:
        by_rule: dict[str, int] = {}
        for scan in self.scans:
            for finding in scan.get("findings", []):
                key = finding.get("rule_id", "UNKNOWN")
                by_rule[key] = by_rule.get(key, 0) + 1
        return {
            "session_id": self.session_id,
            "avd_name": self.avd_name,
            "udid": self.udid,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "apk": self.apk_metadata,
            "device": self.device_info,
            "scans": self.scans,
            "totals": {
                "scans": len(self.scans),
                "findings": self.finding_count,
                "by_rule": by_rule,
            },
        }


class SessionManager:
    def __init__(self) -> None:
        self._session: Session | None = None
        self._lock = asyncio.Lock()

    @property
    def current(self) -> Session | None:
        return self._session

    def create(self, avd_name: str, apk_id: str, apk_metadata: dict[str, Any]) -> Session:
        if self._session and self._session.status in ACTIVE_STATUSES:
            raise ConflictError("已有进行中的检测会话，请先结束。")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"{stamp}-{secrets.token_hex(3)}"
        session = Session(
            session_id=session_id,
            avd_name=avd_name,
            apk_id=apk_id,
            apk_metadata=apk_metadata,
            run_dir=get_settings().runs_dir / session_id,
        )
        self._session = session
        session.persist()
        return session

    def require_active(self) -> Session:
        if not self._session or self._session.status not in ACTIVE_STATUSES:
            raise NoSessionError("当前没有进行中的检测会话。")
        return self._session

    async def cleanup_on_shutdown(self) -> None:
        """Best-effort cleanup so uvicorn restarts don't orphan emulators."""
        session = self._session
        if not session or session.status not in ACTIVE_STATUSES:
            return
        from .services import avd_manager

        def _cleanup() -> None:
            wsscrcpy_manager.stop(session.wsscrcpy_proc)
            avd_manager.kill_emulator(session.udid, session.emulator_proc)

        await asyncio.to_thread(_cleanup)


class ConflictError(RuntimeError):
    pass


class NoSessionError(RuntimeError):
    pass


session_manager = SessionManager()
