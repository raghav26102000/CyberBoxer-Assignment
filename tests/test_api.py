import io
from app.config import API_KEY, API_KEY_HEADER_NAME

AUTH_HEADERS = {API_KEY_HEADER_NAME: API_KEY}


CUSTOMER_CSV = b"""customer_id,name,age,city,state
C001,John Smith,35,Dallas,TX
C002,Alice Johnson,42,San Francisco,CA
"""

POLICY_CSV = b"""policy_id,customer_id,policy_issue_date,coverage_limit,deductible,state
P1001,C001,2022-01-10,50000,1000,TX
P1002,C002,2021-07-15,150000,5000,CA
P9999,C999,2021-01-01,50000,1000,TX
"""

CLAIM_CSV = b"""claim_id,policy_id,loss_date,loss_amount,cause
CL001,P1001,2023-06-15,25000,Fire
CL002,P1002,2023-01-20,50000,Flood
CL003,P0000,2023-01-20,50000,Flood
CL004,P1001,2020-01-01,-500,Fire
"""


def _files():
    return {
        "customer_file": ("customer.csv", io.BytesIO(CUSTOMER_CSV), "text/csv"),
        "policy_file": ("policy.csv", io.BytesIO(POLICY_CSV), "text/csv"),
        "claim_file": ("claims.csv", io.BytesIO(CLAIM_CSV), "text/csv"),
    }


def test_upload_inserts_valid_and_rejects_invalid(client):
    resp = client.post("/upload", files=_files(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()

    assert data["customers"]["inserted"] == 2
    assert data["policies"]["inserted"] == 2  # P9999 rejected: unknown customer
    assert data["policies"]["rejected"] == 1
    assert data["claims"]["inserted"] == 2  # CL003 (bad policy), CL004 (negative) rejected
    assert data["claims"]["rejected"] == 2


def test_upload_without_api_key_is_rejected(client):
    resp = client.post("/upload", files=_files())
    assert resp.status_code == 401
    assert resp.json()["error"] == "Unauthorized"


def test_upload_with_wrong_api_key_is_rejected(client):
    resp = client.post("/upload", files=_files(), headers={API_KEY_HEADER_NAME: "wrong-key"})
    assert resp.status_code == 401


def test_claim_detail_returns_payout_and_fraud_flag(client):
    client.post("/upload", files=_files(), headers=AUTH_HEADERS)
    resp = client.get("/claims/CL002")
    assert resp.status_code == 200
    body = resp.json()
    assert body["claim"]["claim_id"] == "CL002"
    # Flood in CA: 50000 - 5000 deductible - 10%*50000 = 40000
    assert body["calculated_payout"] == 40000
    assert body["customer_flagged_potential_fraud"] is False


def test_claim_not_found_returns_404(client):
    resp = client.get("/claims/DOES_NOT_EXIST")
    assert resp.status_code == 404
    assert resp.json()["error"] == "NotFound"


PAGINATION_CUSTOMER_CSV = b"""customer_id,name,age,city,state
C001,John Smith,35,Dallas,TX
"""

PAGINATION_POLICY_CSV = b"""policy_id,customer_id,policy_issue_date,coverage_limit,deductible,state
P1001,C001,2020-01-01,100000,1000,TX
"""

PAGINATION_CLAIM_CSV = b"""claim_id,policy_id,loss_date,loss_amount,cause
CL101,P1001,2023-01-01,10000,Fire
CL102,P1001,2023-02-01,10000,Fire
CL103,P1001,2023-03-01,10000,Fire
CL104,P1001,2023-04-01,10000,Fire
CL105,P1001,2023-05-01,10000,Fire
"""


def test_claims_search_pagination(client):
    files = {
        "customer_file": ("customer.csv", io.BytesIO(PAGINATION_CUSTOMER_CSV), "text/csv"),
        "policy_file": ("policy.csv", io.BytesIO(PAGINATION_POLICY_CSV), "text/csv"),
        "claim_file": ("claims.csv", io.BytesIO(PAGINATION_CLAIM_CSV), "text/csv"),
    }
    resp = client.post("/upload", files=files, headers=AUTH_HEADERS)
    assert resp.status_code == 201
    assert resp.json()["claims"]["inserted"] == 5

    # First page: 2 rows, but total reflects all 5 matching rows, not just the page
    page1 = client.get("/claims", params={"limit": 2, "offset": 0, "sort_by": "loss_date", "order": "asc"})
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["total"] == 5
    assert body1["limit"] == 2
    assert body1["offset"] == 0
    assert len(body1["items"]) == 2
    assert [c["claim_id"] for c in body1["items"]] == ["CL101", "CL102"]

    # Second page: next 2 rows, no overlap with page 1
    page2 = client.get("/claims", params={"limit": 2, "offset": 2, "sort_by": "loss_date", "order": "asc"})
    body2 = page2.json()
    assert body2["total"] == 5
    assert [c["claim_id"] for c in body2["items"]] == ["CL103", "CL104"]

    # Last page: only 1 row left, even though limit asked for 2
    page3 = client.get("/claims", params={"limit": 2, "offset": 4, "sort_by": "loss_date", "order": "asc"})
    body3 = page3.json()
    assert body3["total"] == 5
    assert [c["claim_id"] for c in body3["items"]] == ["CL105"]


STATE_TOGGLE_CUSTOMER_CSV = b"""customer_id,name,age,city,state
C201,Dana Lee,40,Austin,TX
"""

STATE_TOGGLE_POLICY_CSV = b"""policy_id,customer_id,policy_issue_date,coverage_limit,deductible,state
P2001,C201,2020-01-01,100000,1000,CA
"""

STATE_TOGGLE_CLAIM_CSV = b"""claim_id,policy_id,loss_date,loss_amount,cause
CL201,P2001,2023-01-01,10000,Fire
"""


def test_state_report_basis_toggle_produces_different_results(client):
    # Customer lives in TX, but the policy was issued in CA -- the exact
    # case the basis toggle exists for. Confirms the two modes aren't just
    # cosmetically different query params returning the same rows.
    files = {
        "customer_file": ("customer.csv", io.BytesIO(STATE_TOGGLE_CUSTOMER_CSV), "text/csv"),
        "policy_file": ("policy.csv", io.BytesIO(STATE_TOGGLE_POLICY_CSV), "text/csv"),
        "claim_file": ("claims.csv", io.BytesIO(STATE_TOGGLE_CLAIM_CSV), "text/csv"),
    }
    resp = client.post("/upload", files=files, headers=AUTH_HEADERS)
    assert resp.status_code == 201
    assert resp.json()["claims"]["inserted"] == 1

    by_policy = client.get("/reports/state", params={"basis": "policy"}).json()
    by_customer = client.get("/reports/state", params={"basis": "customer"}).json()

    assert by_policy["basis"] == "policy"
    assert by_customer["basis"] == "customer"
    assert [r["state"] for r in by_policy["rows"]] == ["CA"]
    assert [r["state"] for r in by_customer["rows"]] == ["TX"]


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
