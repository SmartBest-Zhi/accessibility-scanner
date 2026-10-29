"""Detection session lifecycle: start / status / scan / scans / end / summary."""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services import avd_manager, capture, scanner, wsscrcpy_manager
from ..state import ConflictError, NoSessionError, Session, session_manager
from .apk import load_apk

router = APIRouter(prefix="/session", tags=["session"])


class StartRequest(BaseModel):
    avd_name: str
    apk_id: str


class ScanRequest(BaseModel):
    label: str = ""


def _run_start(session: Session) -> None:
    """Blocking startup pipeline — runs in a worker thread."""
    try:
        session.transition("booting", f"冷启动 AVD：{session.avd_name}")
        udid, proc = avd_manager.cold_start(session.avd_name)
        session.udid, session.emulator_proc = udid, proc
        session.persist()

        apk_path, _ = load_apk(session.apk_id)
        session.transition("installing", f"覆盖安装 {session.apk_metadata.get('file_name')}")
        avd_manager.install_apk(udid, apk_path)

        package = session.apk_metadata.get("application_id")
        if not package:
            raise RuntimeError("APK 缺少 application_id，无法自动启动。请检查 apkanalyzer 是否可用。")
        session.transition("launching", f"启动应用 {package}")
        avd_manager.launch_app(udid, package)

        session.transition("launching", "启动 ws-scrcpy 实时画面服务")
        session.wsscrcpy_proc = wsscrcpy_manager.start()

        session.device_info = {
            "udid": udid,
            "density_dpi": capture.read_density_dpi(udid),
            "api_level": capture.read_api_level(udid),
        }
        session.transition("ready", "就绪，可操作模拟器并点击 Scan")
    except Exception as exc:
        session.fail(str(exc))
        # Best-effort cleanup so a half-started session leaves nothing running.
        try:
            wsscrcpy_manager.stop(session.wsscrcpy_proc)
            avd_manager.kill_emulator(session.udid, session.emulator_proc)
        except Exception:
            pass


def _run_scan(session: Session, scan_id_holder: dict, label: str) -> None:
    """Blocking scan pipeline — runs in a worker thread."""
    try:
        session.transition("scanning", f"扫描中：{label or '未命名页面'}")
        scan = scanner.perform_scan(session, label)
        scan_id_holder["scan_id"] = scan["scan_id"]
        session.transition("ready", f"扫描完成 {scan['scan_id']}，{len(scan['findings'])} 个候选问题")
    except Exception as exc:
        session.transition("ready", f"扫描失败：{exc}")
        scan_id_holder["error"] = str(exc)


def _run_end(session: Session) -> None:
    """Blocking teardown — runs in a worker thread."""
    try:
        session.transition("ending", "关闭 AVD 与 ws-scrcpy")
        # Belt-and-braces: restore font scale in case a scan died mid-probe.
        if session.udid:
            try:
                capture.set_font_scale(session.udid, 1.0)
            except Exception:
                pass
        wsscrcpy_manager.stop(session.wsscrcpy_proc)
        avd_manager.kill_emulator(session.udid, session.emulator_proc)
        session.ended_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        session.transition("ended", "检测结束")
    except Exception as exc:
        session.fail(f"结束会话时出错：{exc}")


@router.post("/start", status_code=202)
async def start_session(body: StartRequest) -> dict:
    _, metadata = load_apk(body.apk_id)  # 404s if the apk_id is unknown
    try:
        session = session_manager.create(body.avd_name, body.apk_id, metadata)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.current_task = asyncio.create_task(asyncio.to_thread(_run_start, session))
    return {"session_id": session.session_id, "status": session.status}


@router.get("/status")
def session_status() -> dict:
    session = session_manager.current
    if not session:
        return {"session_id": None, "status": "idle", "log": []}
    return {
        "session_id": session.session_id,
        "status": session.status,
        "error": session.error,
        "avd_name": session.avd_name,
        "udid": session.udid,
        "stream_url": session.stream_url,
        "scan_count": len(session.scans),
        "finding_count": session.finding_count,
        "apk_id": session.apk_id,
        "log": session.log[-20:],
    }


@router.post("/scan", status_code=202)
async def scan(body: ScanRequest) -> dict:
    try:
        session = session_manager.require_active()
    except NoSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if session.status != "ready":
        raise HTTPException(status_code=409, detail=f"当前状态为 {session.status}，暂不能扫描。")
    holder: dict = {}
    task = asyncio.create_task(asyncio.to_thread(_run_scan, session, holder, body.label))
    session.current_task = task

    # The scan takes 5-15s (dual-snapshot). Wait briefly so the caller usually
    # gets the finished scan_id in one round-trip; fall back to 202 polling.
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=60)
    except asyncio.TimeoutError:
        return {"status": "scanning"}
    if "error" in holder:
        raise HTTPException(status_code=500, detail=holder["error"])
    return {"scan_id": holder.get("scan_id"), "status": "ready"}


@router.get("/scans")
def list_scans() -> dict:
    session = session_manager.current
    if not session:
        return {"scans": []}
    return {"scans": session.scans}


@router.get("/scans/{scan_id}/screenshot")
def scan_screenshot(scan_id: str) -> FileResponse:
    session = session_manager.current
    if not session:
        raise HTTPException(status_code=404, detail="没有会话")
    # scan_id is validated against the recorded scans — no path traversal.
    if not any(scan["scan_id"] == scan_id for scan in session.scans):
        raise HTTPException(status_code=404, detail=f"未知扫描：{scan_id}")
    path = session.run_dir / scan_id / "screenshot.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="截图文件不存在")
    return FileResponse(path, media_type="image/png")


@router.post("/end")
async def end_session() -> dict:
    try:
        session = session_manager.require_active()
    except NoSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    task = asyncio.create_task(asyncio.to_thread(_run_end, session))
    session.current_task = task
    await asyncio.wait_for(asyncio.shield(task), timeout=60)
    return session.summary()


@router.get("/summary")
def session_summary() -> dict:
    session = session_manager.current
    if not session:
        raise HTTPException(status_code=404, detail="没有会话")
    return session.summary()
