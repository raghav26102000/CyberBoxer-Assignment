"""
All claim payout / fraud logic lives here in one place so it can be unit
tested independently of the API and the database.

Payout formula (documented as an assumption in the README, since the
assignment doesn't fully specify ordering):

    1. payout = loss_amount - policy.deductible
    2. if cause == "Flood" and policy.state == "CA":
           payout -= 0.10 * loss_amount      # extra CA flood deductible
    3. if customer.age < 18:
           payout *= 0.5                     # minor payout reduction
    4. payout = clamp(payout, 0, policy.coverage_limit)

Steps run in this order because deductibles are subtracted from the raw
loss first, the minor reduction is applied to whatever is left after
deductibles, and the coverage-limit cap is the final ceiling regardless
of how we got there.
"""
from app.config import (
    MINOR_AGE_THRESHOLD,
    MINOR_PAYOUT_MULTIPLIER,
    CA_FLOOD_EXTRA_DEDUCTIBLE_RATE,
    FRAUD_CLAIM_COUNT_THRESHOLD,
)


def calculate_payout(
    loss_amount: float,
    deductible: float,
    coverage_limit: float,
    policy_state: str,
    cause: str,
    customer_age: int,
) -> float:
    payout = loss_amount - deductible

    if cause.strip().lower() == "flood" and policy_state.strip().upper() == "CA":
        payout -= CA_FLOOD_EXTRA_DEDUCTIBLE_RATE * loss_amount

    if customer_age < MINOR_AGE_THRESHOLD:
        payout *= MINOR_PAYOUT_MULTIPLIER

    payout = max(0.0, payout)
    payout = min(payout, coverage_limit)

    return round(payout, 2)


def is_potential_fraud(claim_count: int) -> bool:
    return claim_count > FRAUD_CLAIM_COUNT_THRESHOLD
