"""FastAPI entry point: uvicorn app.main:app --port 8000 (from backend/)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import apk, session, system
from .state import session_manager

app = FastAPI(title="App Accessibility Scanner", version="0.1.0")

# The Vite dev proxy makes CORS unnecessary in the standard setup; this stays
# as a permissive fallback for direct cross-origin access during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router, prefix="/api")
app.include_router(apk.router, prefix="/api")
app.include_router(session.router, prefix="/api")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await session_manager.cleanup_on_shutdown()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=get_settings().BACKEND_PORT)
