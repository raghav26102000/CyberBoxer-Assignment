"""
Reporting queries. The assignment explicitly requires at least two raw SQL
queries for reporting (as opposed to pure ORM/Pandas) -- both live here.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import FRAUD_CLAIM_COUNT_THRESHOLD


# Raw SQL #1: state-level rollup (total claims, avg/max/total payout).
#
# "State" is ambiguous in this schema: a customer's own state (where they
# live) and their policy's state (where the policy was issued) can differ,
# and the assignment doesn't say which one a "state report" means. Rather
# than silently pick one and hope, this endpoint takes a `basis` param
# (see reports.py) so either interpretation is one query param away instead
# of a guess baked into the code. Default is "policy" -- see README
# "Assumptions" for the reasoning -- but "customer" is equally one call away.
STATE_REPORT_BY_POLICY_SQL = text("""
    SELECT
        p.state AS state,
        COUNT(c.claim_id) AS total_claims,
        ROUND(AVG(c.final_payout), 2) AS average_payout,
        ROUND(MAX(c.final_payout), 2) AS max_payout,
        ROUND(SUM(c.final_payout), 2) AS total_payout
    FROM claims c
    JOIN policies p ON c.policy_id = p.policy_id
    GROUP BY p.state
    ORDER BY total_payout DESC
""")

STATE_REPORT_BY_CUSTOMER_SQL = text("""
    SELECT
        cu.state AS state,
        COUNT(c.claim_id) AS total_claims,
        ROUND(AVG(c.final_payout), 2) AS average_payout,
        ROUND(MAX(c.final_payout), 2) AS max_payout,
        ROUND(SUM(c.final_payout), 2) AS total_payout
    FROM claims c
    JOIN policies p ON c.policy_id = p.policy_id
    JOIN customers cu ON p.customer_id = cu.customer_id
    GROUP BY cu.state
    ORDER BY total_payout DESC
""")


async def get_state_report(db: AsyncSession, basis: str = "policy") -> list[dict]:
    sql = STATE_REPORT_BY_POLICY_SQL if basis == "policy" else STATE_REPORT_BY_CUSTOMER_SQL
    result = await db.execute(sql)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


# Raw SQL #2: top customers by total payout, with a fraud flag computed
# from the same >5-claims rule used at ingestion time (kept in sync via
# the FRAUD_CLAIM_COUNT_THRESHOLD constant).
TOP_CUSTOMERS_SQL = text("""
    SELECT
        cu.customer_id AS customer_id,
        cu.name AS name,
        cu.city AS city,
        cu.state AS state,
        COUNT(c.claim_id) AS claim_count,
        ROUND(COALESCE(SUM(c.final_payout), 0), 2) AS total_payout,
        CASE WHEN COUNT(c.claim_id) > :fraud_threshold THEN 1 ELSE 0 END AS potential_fraud
    FROM customers cu
    JOIN policies p ON p.customer_id = cu.customer_id
    JOIN claims c ON c.policy_id = p.policy_id
    GROUP BY cu.customer_id, cu.name, cu.city, cu.state
    ORDER BY total_payout DESC
    LIMIT :limit
""")


async def get_top_customers(db: AsyncSession, n: int) -> list[dict]:
    result = await db.execute(
        TOP_CUSTOMERS_SQL, {"limit": n, "fraud_threshold": FRAUD_CLAIM_COUNT_THRESHOLD}
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


# Used internally by the fraud flag on GET /claims/{id}
CLAIM_COUNT_FOR_CUSTOMER_SQL = text("""
    SELECT COUNT(c.claim_id) AS claim_count
    FROM claims c
    JOIN policies p ON c.policy_id = p.policy_id
    WHERE p.customer_id = :customer_id
""")


async def get_claim_count_for_customer(db: AsyncSession, customer_id: str) -> int:
    result = await db.execute(CLAIM_COUNT_FOR_CUSTOMER_SQL, {"customer_id": customer_id})
    row = result.mappings().first()
    return row["claim_count"] if row else 0
