import shutil

from fastapi import APIRouter

from ..config import get_settings
from ..services import apk_analyzer, avd_manager, wsscrcpy_manager

router = APIRouter(tags=["system"])


def _resolve_or_none(name: str, sdk_relative: str | None = None) -> str | None:
    try:
        if sdk_relative:
            from ..adb import resolve_tool

            return resolve_tool(name, sdk_relative)
        return shutil.which(name)
    except RuntimeError:
        return None


@router.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "adb": _resolve_or_none("adb", "platform-tools"),
        "emulator": _resolve_or_none("emulator", "emulator"),
        "apkanalyzer": apk_analyzer.locate_apkanalyzer(),
        "wsscrcpy_installed": wsscrcpy_manager.is_installed(),
        "wsscrcpy_running": wsscrcpy_manager.server_is_up(),
        "android_sdk_root": get_settings().ANDROID_SDK_ROOT,
    }


@router.get("/avds")
def list_avds() -> dict:
    return {"avds": avd_manager.list_avds()}
