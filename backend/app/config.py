"""Backend configuration, resolved from .env (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # Android SDK location; tools on PATH still win over these fallbacks.
    ANDROID_SDK_ROOT: str = r"C:\Software\SDK\Android"

    BACKEND_PORT: int = 8000

    WS_SCRCPY_PORT: int = 8100
    WS_SCRCPY_DIR: Path = BACKEND_DIR / "tools" / "ws-scrcpy"

    BOOT_TIMEOUT_S: int = 240
    FONT_SCALE_TEST_VALUE: float = 1.3

    @property
    def uploads_dir(self) -> Path:
        path = BACKEND_DIR / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def runs_dir(self) -> Path:
        path = BACKEND_DIR / "runs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def wsscrcpy_dir(self) -> Path:
        path = Path(self.WS_SCRCPY_DIR)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
