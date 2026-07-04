from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import TopCustomerOut
from app.services.report_service import get_top_customers
from app.services.cache import get_or_set_async
from app.rate_limit import limiter

router = APIRouter(tags=["Customers"])


@router.get("/customers/top", response_model=list[TopCustomerOut])
@limiter.limit("60/minute")
async def top_customers(request: Request, n: int = Query(10, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    # Cached: this is a full aggregate scan across customers/policies/claims.
    # Cache key includes `n` since different page sizes are different results.
    rows = await get_or_set_async(f"top_customers:{n}", lambda: get_top_customers(db, n))
    return [
        TopCustomerOut(
            customer_id=r["customer_id"],
            name=r["name"],
            city=r["city"],
            state=r["state"],
            total_payout=r["total_payout"],
            claim_count=r["claim_count"],
            potential_fraud=bool(r["potential_fraud"]),
        )
        for r in rows
    ]
