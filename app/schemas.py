from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ---------- Read schemas (ORM -> JSON) ----------

class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    name: str
    age: int
    city: str
    state: str


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    customer_id: str
    policy_issue_date: date
    coverage_limit: float
    deductible: float
    state: str


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_id: str
    policy_id: str
    loss_date: date
    loss_amount: float
    cause: str
    final_payout: float
    created_at: Optional[datetime] = None


class ClaimSearchResult(BaseModel):
    items: list[ClaimOut]
    total: int
    limit: int
    offset: int


class ClaimDetailOut(BaseModel):
    """Response for GET /claims/{claim_id}: claim + customer + policy + payout."""
    claim: ClaimOut
    customer: CustomerOut
    policy: PolicyOut
    calculated_payout: float
    customer_flagged_potential_fraud: bool


# ---------- Upload response ----------

class UploadResult(BaseModel):
    total_records: int
    inserted: int
    rejected: int
    errors: list[str]


class UploadResponse(BaseModel):
    customers: UploadResult
    policies: UploadResult
    claims: UploadResult
    total_records: int
    inserted: int
    rejected: int
    errors: list[str]


# ---------- Reports ----------

class TopCustomerOut(BaseModel):
    customer_id: str
    name: str
    city: str
    state: str
    total_payout: float
    claim_count: int
    potential_fraud: bool


class StateReportOut(BaseModel):
    state: str
    total_claims: int
    average_payout: float
    max_payout: float
    total_payout: float


class StateReportResponse(BaseModel):
    basis: str  # "policy" or "customer" -- which state field these rows are grouped by
    rows: list[StateReportOut]


# ---------- Health ----------

class HealthOut(BaseModel):
    status: str
    database: str
    uptime: str


# ---------- Error ----------

class ErrorResponse(BaseModel):
    error: str
    message: str
