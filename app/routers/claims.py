from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, asc, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Claim, Policy, Customer
from app.schemas import ClaimDetailOut, ClaimOut, ClaimSearchResult
from app.exceptions import NotFoundError, ValidationError
from app.services.report_service import get_claim_count_for_customer
from app.config import FRAUD_CLAIM_COUNT_THRESHOLD
from app.rate_limit import limiter

router = APIRouter(tags=["Claims"])

SORTABLE_FIELDS = {
    "loss_date": Claim.loss_date,
    "loss_amount": Claim.loss_amount,
    "final_payout": Claim.final_payout,
    "cause": Claim.cause,
}


@router.get("/claims/{claim_id}", response_model=ClaimDetailOut)
@limiter.limit("120/minute")
async def get_claim_detail(request: Request, claim_id: str, db: AsyncSession = Depends(get_db)):
    claim = (
        await db.execute(select(Claim).where(Claim.claim_id == claim_id))
    ).scalar_one_or_none()
    if not claim:
        raise NotFoundError(f"Claim '{claim_id}' does not exist")

    policy = (
        await db.execute(select(Policy).where(Policy.policy_id == claim.policy_id))
    ).scalar_one_or_none()
    customer = (
        await db.execute(select(Customer).where(Customer.customer_id == policy.customer_id))
    ).scalar_one_or_none()

    claim_count = await get_claim_count_for_customer(db, customer.customer_id)

    return ClaimDetailOut(
        claim=ClaimOut.model_validate(claim),
        customer=customer,
        policy=policy,
        calculated_payout=claim.final_payout,
        customer_flagged_potential_fraud=claim_count > FRAUD_CLAIM_COUNT_THRESHOLD,
    )


@router.get("/claims", response_model=ClaimSearchResult)
@limiter.limit("120/minute")
async def search_claims(
    request: Request,
    city: Optional[str] = Query(None, description="Filter by customer city"),
    state: Optional[str] = Query(None, description="Filter by policy state"),
    cause: Optional[str] = Query(None, description="Filter by claim cause"),
    date_from: Optional[date] = Query(None, description="loss_date >= this date"),
    date_to: Optional[date] = Query(None, description="loss_date <= this date"),
    min_payout: Optional[float] = Query(None, ge=0),
    max_payout: Optional[float] = Query(None, ge=0),
    sort_by: str = Query("loss_date", description="loss_date | loss_amount | final_payout | cause"),
    order: str = Query("desc", description="asc | desc"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip, for paging"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Claim).join(Policy, Claim.policy_id == Policy.policy_id)

    if city:
        stmt = stmt.join(Customer, Policy.customer_id == Customer.customer_id).where(
            Customer.city.ilike(city)
        )
    if state:
        stmt = stmt.where(Policy.state.ilike(state))
    if cause:
        stmt = stmt.where(Claim.cause.ilike(cause))
    if date_from:
        stmt = stmt.where(Claim.loss_date >= date_from)
    if date_to:
        stmt = stmt.where(Claim.loss_date <= date_to)
    if min_payout is not None:
        stmt = stmt.where(Claim.final_payout >= min_payout)
    if max_payout is not None:
        stmt = stmt.where(Claim.final_payout <= max_payout)

    if sort_by not in SORTABLE_FIELDS:
        raise ValidationError(f"sort_by must be one of {list(SORTABLE_FIELDS.keys())}")
    if order not in ("asc", "desc"):
        raise ValidationError("order must be 'asc' or 'desc'")

    # Total count reflects the filters but not limit/offset, so the client
    # knows how many rows exist across all pages, not just the page size.
    # Counted from the same filtered statement (before order_by/limit/offset
    # are applied) so it can never disagree with what the filters actually
    # matched.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    sort_col = SORTABLE_FIELDS[sort_by]
    stmt = stmt.order_by(asc(sort_col) if order == "asc" else desc(sort_col))
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    items = result.scalars().all()

    return ClaimSearchResult(items=items, total=total, limit=limit, offset=offset)
