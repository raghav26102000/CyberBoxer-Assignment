from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import StateReportOut, StateReportResponse
from app.services.report_service import get_state_report
from app.services.cache import get_or_set_async
from app.rate_limit import limiter

router = APIRouter(tags=["Reports"])


@router.get("/reports/state", response_model=StateReportResponse)
@limiter.limit("60/minute")
async def state_report(
    request: Request,
    basis: str = Query(
        "policy",
        pattern="^(policy|customer)$",
        description=(
            "Which state field to group by: 'policy' (where the policy was "
            "issued, the default) or 'customer' (where the customer lives). "
            "These can disagree for the same claim -- see README."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_or_set_async(f"reports_state:{basis}", lambda: get_state_report(db, basis))
    return StateReportResponse(
        basis=basis,
        rows=[
            StateReportOut(
                state=r["state"],
                total_claims=r["total_claims"],
                average_payout=r["average_payout"] or 0.0,
                max_payout=r["max_payout"] or 0.0,
                total_payout=r["total_payout"] or 0.0,
            )
            for r in rows
        ],
    )
