"""
Orchestrates the /upload endpoint:
  1. Read each CSV with Pandas.
  2. Clean it (standardize columns, trim whitespace, drop exact duplicate
     rows, coerce types).
  3. Validate row by row (required fields, data types, relationships,
     business rules).
  4. Insert valid rows; collect a human-readable error per rejected row.

Customers are processed first, then policies (which need customers to
exist), then claims (which need policies -- and therefore customers --
to exist). This mirrors the real foreign-key dependency chain.

Runs on an AsyncSession: all DB reads go through explicit `select()`
statements executed with `await db.execute(...)`, since the async
session doesn't support the legacy `Query` API.
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Policy, Claim
from app.services import data_cleaning as dc
from app.services.business_rules import calculate_payout
from app.logging_config import logger


def _empty_result(total: int, error: str) -> dict:
    return {"total_records": total, "inserted": 0, "rejected": total, "errors": [error]}


def _pd_isnull(value) -> bool:
    import pandas as pd
    return pd.isnull(value)


# ---------------------------------------------------------------- customers
async def process_customers(db: AsyncSession, file_bytes: bytes) -> dict:
    required_cols = ["customer_id", "name", "age", "city", "state"]
    raw_df = dc.read_csv_upload(file_bytes)
    total_records = len(raw_df)

    df = dc.standardize_columns(raw_df)
    missing = dc.check_required_columns(df, required_cols)
    if missing:
        return _empty_result(total_records, missing[0])

    df = dc.trim_whitespace(df)
    df = dc.to_numeric_column(df, "age")

    deduped = df.drop_duplicates(keep="first")
    exact_dupe_rows = set(df.index) - set(deduped.index)

    errors: list[str] = [
        f"Row {idx + 2}: duplicate row removed (exact duplicate)" for idx in sorted(exact_dupe_rows)
    ]
    inserted = 0

    existing_ids = (await db.execute(select(Customer.customer_id))).scalars().all()
    seen_ids: set[str] = set(existing_ids)

    for idx, row in deduped.iterrows():
        row_num = idx + 2  # +1 header, +1 to make it 1-indexed for humans

        cust_id = row.get("customer_id")
        name = row.get("name")
        age = row.get("age")
        city = row.get("city")
        state = row.get("state")

        if not cust_id or str(cust_id).lower() == "none":
            errors.append(f"Row {row_num}: missing customer_id")
            continue
        if cust_id in seen_ids:
            errors.append(f"Row {row_num}: duplicate customer_id '{cust_id}'")
            continue
        if not name:
            errors.append(f"Row {row_num}: missing name for customer '{cust_id}'")
            continue
        if age is None or (isinstance(age, float) and age != age):  # NaN check
            errors.append(f"Row {row_num}: invalid or missing age for customer '{cust_id}'")
            continue
        if age < 0 or age > 130:
            errors.append(f"Row {row_num}: age out of valid range for customer '{cust_id}'")
            continue
        if not city or not state:
            errors.append(f"Row {row_num}: missing city/state for customer '{cust_id}'")
            continue

        db.add(Customer(
            customer_id=str(cust_id),
            name=str(name),
            age=int(age),
            city=str(city),
            state=str(state).upper(),
        ))
        seen_ids.add(cust_id)
        inserted += 1

    await db.flush()
    rejected = total_records - inserted
    logger.info(f"Customers upload: total={total_records} inserted={inserted} rejected={rejected}")
    return {"total_records": total_records, "inserted": inserted, "rejected": rejected, "errors": errors}


# ------------------------------------------------------------------ policies
async def process_policies(db: AsyncSession, file_bytes: bytes) -> dict:
    required_cols = ["policy_id", "customer_id", "policy_issue_date", "coverage_limit", "deductible", "state"]
    raw_df = dc.read_csv_upload(file_bytes)
    total_records = len(raw_df)

    df = dc.standardize_columns(raw_df)
    missing = dc.check_required_columns(df, required_cols)
    if missing:
        return _empty_result(total_records, missing[0])

    df = dc.trim_whitespace(df)
    df = dc.to_numeric_column(df, "coverage_limit")
    df = dc.to_numeric_column(df, "deductible")
    df = dc.parse_date_column(df, "policy_issue_date")

    deduped = df.drop_duplicates(subset=[c for c in df.columns], keep="first")
    exact_dupe_rows = set(df.index) - set(deduped.index)

    errors: list[str] = [
        f"Row {idx + 2}: duplicate row removed (exact duplicate)" for idx in sorted(exact_dupe_rows)
    ]
    inserted = 0

    seen_policy_ids: set[str] = set((await db.execute(select(Policy.policy_id))).scalars().all())
    valid_customer_ids: set[str] = set((await db.execute(select(Customer.customer_id))).scalars().all())

    for idx, row in deduped.iterrows():
        row_num = idx + 2

        policy_id = row.get("policy_id")
        customer_id = row.get("customer_id")
        issue_date = row.get("policy_issue_date")
        coverage_limit = row.get("coverage_limit")
        deductible = row.get("deductible")
        state = row.get("state")

        if not policy_id:
            errors.append(f"Row {row_num}: missing policy_id")
            continue
        if policy_id in seen_policy_ids:
            errors.append(f"Row {row_num}: duplicate policy_id '{policy_id}'")
            continue
        if not customer_id or customer_id not in valid_customer_ids:
            errors.append(f"Row {row_num}: policy '{policy_id}' references non-existent customer '{customer_id}' (rejected)")
            continue
        if _pd_isnull(issue_date):
            errors.append(f"Row {row_num}: invalid policy_issue_date for policy '{policy_id}'")
            continue
        if coverage_limit is None or coverage_limit != coverage_limit or coverage_limit <= 0:
            errors.append(f"Row {row_num}: invalid coverage_limit for policy '{policy_id}'")
            continue
        if deductible is None or deductible != deductible or deductible < 0:
            errors.append(f"Row {row_num}: invalid deductible for policy '{policy_id}'")
            continue
        if not state:
            errors.append(f"Row {row_num}: missing state for policy '{policy_id}'")
            continue

        db.add(Policy(
            policy_id=str(policy_id),
            customer_id=str(customer_id),
            policy_issue_date=issue_date.date() if hasattr(issue_date, "date") else issue_date,
            coverage_limit=float(coverage_limit),
            deductible=float(deductible),
            state=str(state).upper(),
        ))
        seen_policy_ids.add(policy_id)
        inserted += 1

    await db.flush()
    rejected = total_records - inserted
    logger.info(f"Policies upload: total={total_records} inserted={inserted} rejected={rejected}")
    return {"total_records": total_records, "inserted": inserted, "rejected": rejected, "errors": errors}


# -------------------------------------------------------------------- claims
async def process_claims(db: AsyncSession, file_bytes: bytes) -> dict:
    required_cols = ["claim_id", "policy_id", "loss_date", "loss_amount", "cause"]
    raw_df = dc.read_csv_upload(file_bytes)
    total_records = len(raw_df)

    df = dc.standardize_columns(raw_df)
    missing = dc.check_required_columns(df, required_cols)
    if missing:
        return _empty_result(total_records, missing[0])

    df = dc.trim_whitespace(df)
    df = dc.to_numeric_column(df, "loss_amount")
    df = dc.parse_date_column(df, "loss_date")

    deduped = df.drop_duplicates(keep="first")
    exact_dupe_rows = set(df.index) - set(deduped.index)

    errors: list[str] = [
        f"Row {idx + 2}: duplicate row removed (exact duplicate)" for idx in sorted(exact_dupe_rows)
    ]
    inserted = 0

    seen_claim_ids: set[str] = set((await db.execute(select(Claim.claim_id))).scalars().all())

    # Pull policy + customer lookups once for speed instead of a query per row.
    policies = {p.policy_id: p for p in (await db.execute(select(Policy))).scalars().all()}
    customers = {c.customer_id: c for c in (await db.execute(select(Customer))).scalars().all()}

    today = date.today()

    for idx, row in deduped.iterrows():
        row_num = idx + 2

        claim_id = row.get("claim_id")
        policy_id = row.get("policy_id")
        loss_date = row.get("loss_date")
        loss_amount = row.get("loss_amount")
        cause = row.get("cause")

        if not claim_id:
            errors.append(f"Row {row_num}: missing claim_id")
            continue
        if claim_id in seen_claim_ids:
            errors.append(f"Row {row_num}: duplicate claim_id '{claim_id}'")
            continue
        if not policy_id or policy_id not in policies:
            errors.append(f"Row {row_num}: claim '{claim_id}' references policy not found '{policy_id}'")
            continue

        policy = policies[policy_id]
        customer = customers.get(policy.customer_id)
        if customer is None:
            errors.append(f"Row {row_num}: claim '{claim_id}' policy has no matching customer")
            continue

        if _pd_isnull(loss_date):
            errors.append(f"Row {row_num}: invalid date for claim '{claim_id}'")
            continue
        loss_date_val = loss_date.date() if hasattr(loss_date, "date") else loss_date

        if loss_amount is None or loss_amount != loss_amount:
            errors.append(f"Row {row_num}: invalid loss_amount for claim '{claim_id}'")
            continue
        if loss_amount < 0:
            errors.append(f"Row {row_num}: loss amount cannot be negative for claim '{claim_id}'")
            continue
        if loss_date_val > today:
            errors.append(f"Row {row_num}: loss date cannot be in the future for claim '{claim_id}'")
            continue
        if loss_date_val < policy.policy_issue_date:
            errors.append(f"Row {row_num}: claim date earlier than policy issue date for claim '{claim_id}'")
            continue
        if not cause:
            errors.append(f"Row {row_num}: missing cause for claim '{claim_id}'")
            continue

        final_payout = calculate_payout(
            loss_amount=float(loss_amount),
            deductible=policy.deductible,
            coverage_limit=policy.coverage_limit,
            policy_state=policy.state,
            cause=str(cause),
            customer_age=customer.age,
        )

        db.add(Claim(
            claim_id=str(claim_id),
            policy_id=str(policy_id),
            loss_date=loss_date_val,
            loss_amount=float(loss_amount),
            cause=str(cause),
            final_payout=final_payout,
        ))
        seen_claim_ids.add(claim_id)
        inserted += 1

    await db.flush()
    rejected = total_records - inserted
    logger.info(f"Claims upload: total={total_records} inserted={inserted} rejected={rejected}")
    return {"total_records": total_records, "inserted": inserted, "rejected": rejected, "errors": errors}


async def process_upload(db: AsyncSession, customer_bytes: bytes, policy_bytes: bytes, claim_bytes: bytes) -> dict:
    customers_result = await process_customers(db, customer_bytes)
    policies_result = await process_policies(db, policy_bytes)
    claims_result = await process_claims(db, claim_bytes)

    await db.commit()

    total_records = (
        customers_result["total_records"] + policies_result["total_records"] + claims_result["total_records"]
    )
    inserted = customers_result["inserted"] + policies_result["inserted"] + claims_result["inserted"]
    rejected = customers_result["rejected"] + policies_result["rejected"] + claims_result["rejected"]
    all_errors = customers_result["errors"] + policies_result["errors"] + claims_result["errors"]

    return {
        "customers": customers_result,
        "policies": policies_result,
        "claims": claims_result,
        "total_records": total_records,
        "inserted": inserted,
        "rejected": rejected,
        "errors": all_errors,
    }
