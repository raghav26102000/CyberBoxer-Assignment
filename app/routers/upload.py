from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import UploadResponse
from app.services.upload_service import process_upload
from app.services.audit import write_upload_audit_record
from app.services.cache import invalidate_all
from app.exceptions import BadRequestError
from app.logging_config import logger
from app.auth import require_api_key
from app.rate_limit import limiter
from app.config import UPLOAD_RATE_LIMIT

router = APIRouter(tags=["Upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(UPLOAD_RATE_LIMIT)
async def upload_csvs(
    request: Request,
    background_tasks: BackgroundTasks,
    customer_file: UploadFile = File(..., description="customer.csv"),
    policy_file: UploadFile = File(..., description="policy.csv"),
    claim_file: UploadFile = File(..., description="claims.csv"),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts the three CSV files, cleans and validates them with Pandas,
    then inserts valid rows in dependency order: customers -> policies
    -> claims. Invalid rows are rejected individually and reported back;
    valid rows are still inserted (partial success is allowed by design,
    since rejecting the whole batch over one bad row isn't useful for a
    real ingestion pipeline).

    Requires the X-API-Key header. Rate limited separately (and more
    strictly) from read endpoints since it's the only endpoint that
    writes and does real work (Pandas parsing + row-by-row validation).
    """
    for f, label in [(customer_file, "customer_file"), (policy_file, "policy_file"), (claim_file, "claim_file")]:
        if not f.filename or not f.filename.lower().endswith(".csv"):
            raise BadRequestError(f"{label} must be a .csv file")

    customer_bytes = await customer_file.read()
    policy_bytes = await policy_file.read()
    claim_bytes = await claim_file.read()

    logger.info("Upload request received: %s, %s, %s" % (
        customer_file.filename, policy_file.filename, claim_file.filename
    ))

    result = await process_upload(db, customer_bytes, policy_bytes, claim_bytes)

    # Reports read from the DB and cache results; a write just happened,
    # so any cached report is now stale and must be dropped immediately
    # rather than waiting out its TTL.
    invalidate_all()

    logger.info(
        "Upload complete: total=%s inserted=%s rejected=%s"
        % (result["total_records"], result["inserted"], result["rejected"])
    )

    # Audit logging happens after the response is prepared but doesn't
    # block returning it to the client -- it's disk I/O that has no
    # bearing on whether the upload itself succeeded.
    background_tasks.add_task(write_upload_audit_record, result)

    return result
