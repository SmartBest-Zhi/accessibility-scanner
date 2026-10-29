"""Manage the ws-scrcpy standalone web server as a child process.

ws-scrcpy is installed manually (see backend/README.md):
    cd backend/tools && git clone https://github.com/NetrisTV/ws-scrcpy
    cd ws-scrcpy
    # 本仓库的构建配置已关闭 INCLUDE_ADB_SHELL（node-pty 无法在 Node 22 下构建，
    # 我们也不需要浏览器终端功能）：webpack/default.build.config.json
    npm install --ignore-scripts
    npm run dist
    cd dist && npm install --omit=dev --ignore-scripts

Runtime notes (verified against the cloned 0.9.0-dev source):
* The server is `node dist/index.js`; there is no `--port` CLI flag — the port
  comes from a YAML/JSON config whose path is passed via the WS_SCRCPY_CONFIG
  environment variable. This module writes that config on every start.
* The stream deep link is  /#!action=stream&player=mse&udid=<udid>.

The frontend embeds the stream page in an iframe; bidirectional control is
handled entirely by ws-scrcpy's own websocket, never by this backend.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from typing import Any

from ..adb import run_command
from ..config import get_settings

_CONFIG_NAME = "backend.yaml"


def _dist_dir() -> Any:
    return get_settings().wsscrcpy_dir / "dist"


def is_installed() -> bool:
    return (_dist_dir() / "index.js").is_file()


def server_is_up() -> bool:
    url = f"http://127.0.0.1:{get_settings().WS_SCRCPY_PORT}/"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def _write_config() -> str:
    settings = get_settings()
    config_path = settings.wsscrcpy_dir / _CONFIG_NAME
    config_path.write_text(
        f"server:\n  - secure: false\n    port: {settings.WS_SCRCPY_PORT}\n",
        encoding="utf-8",
    )
    return str(config_path)


def start() -> subprocess.Popen[Any]:
    """Start ws-scrcpy and wait until its web server answers."""
    settings = get_settings()
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Cannot find node on PATH; Node.js is required for ws-scrcpy.")
    if not is_installed():
        raise RuntimeError(
            f"ws-scrcpy is not built under {settings.wsscrcpy_dir} (missing dist/index.js). "
            "See backend/README.md for the one-time setup."
        )
    if server_is_up():
        raise RuntimeError(
            f"Port {settings.WS_SCRCPY_PORT} already serves HTTP — a ws-scrcpy instance "
            "may already be running. Stop it first."
        )

    env = dict(os.environ)
    env["WS_SCRCPY_CONFIG"] = _write_config()
    # ws-scrcpy discovers devices via adb; make sure the SDK is visible.
    env.setdefault("ANDROID_HOME", settings.ANDROID_SDK_ROOT)
    env.setdefault("ANDROID_SDK_ROOT", settings.ANDROID_SDK_ROOT)

    proc = subprocess.Popen(
        [node, "index.js"],
        cwd=_dist_dir(),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if server_is_up():
            return proc
        if proc.poll() is not None:
            raise RuntimeError("ws-scrcpy exited before its web server became ready.")
        time.sleep(1)
    stop(proc)
    raise TimeoutError("ws-scrcpy web server did not become ready within 30 seconds.")


def stop(proc: subprocess.Popen[Any] | None) -> None:
    if proc and proc.poll() is None:
        try:
            run_command(["taskkill", "/PID", str(proc.pid), "/T", "/F"], timeout=20)
        except Exception:
            pass


def stream_url(udid: str) -> str:
    port = get_settings().WS_SCRCPY_PORT
    return f"http://127.0.0.1:{port}/#!action=stream&player=mse&udid={udid}"
