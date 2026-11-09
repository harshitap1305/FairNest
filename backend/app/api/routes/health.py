"""Health, admin, and reporting routes."""

from fastapi import APIRouter, Depends
from app.api.deps import get_db

# ── health ────────────────────────────────────────────────────────────────────
router = APIRouter(tags=["health"])

@router.get("/health/live")
async def live():
    return {"status": "ok"}

@router.get("/health/ready")
async def ready(db=Depends(get_db)):
    try:
        await db.command("ping")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})
