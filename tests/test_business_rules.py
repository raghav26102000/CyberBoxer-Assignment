from app.services.business_rules import calculate_payout, is_potential_fraud


def test_basic_payout_subtracts_deductible():
    payout = calculate_payout(10000, 1000, 50000, "TX", "Fire", 35)
    assert payout == 9000


def test_ca_flood_applies_extra_10_percent_deductible():
    # loss 50000, deductible 5000 -> 45000, minus 10% of loss (5000) -> 40000
    payout = calculate_payout(50000, 5000, 150000, "CA", "Flood", 42)
    assert payout == 40000


def test_flood_outside_ca_does_not_get_extra_deductible():
    payout = calculate_payout(50000, 5000, 150000, "TX", "Flood", 42)
    assert payout == 45000


def test_minor_gets_half_payout():
    payout = calculate_payout(10000, 1000, 50000, "TX", "Fire", 16)
    assert payout == 4500  # (10000-1000) * 0.5


def test_payout_capped_at_coverage_limit():
    payout = calculate_payout(180000, 10000, 50000, "NY", "Earthquake", 29)
    assert payout == 50000


def test_payout_never_negative():
    payout = calculate_payout(1000, 5000, 50000, "TX", "Fire", 35)
    assert payout == 0


def test_fraud_flag_threshold():
    assert is_potential_fraud(5) is False
    assert is_potential_fraud(6) is True
