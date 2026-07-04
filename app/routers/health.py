import time
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import HealthOut
from app.rate_limit import limiter

router = APIRouter(tags=["Health"])

_start_time = time.time()


def _format_uptime(seconds: float) -> str:
    hours, rem = divmod(int(seconds), 3600)
    minutes, _ = divmod(rem, 60)
    return f"{hours}h {minutes}m"


@router.get("/health", response_model=HealthOut)
@limiter.limit("300/minute")
async def health_check(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
        status = "healthy"
    except Exception:
        db_status = "disconnected"
        status = "unhealthy"

    return HealthOut(
        status=status,
        database=db_status,
        uptime=_format_uptime(time.time() - _start_time),
    )
