# Insurance Claims Processing API

A REST API for ingesting and analyzing insurance claim data, built with async FastAPI, async SQLAlchemy, and Pandas.

## Stack and why

- **FastAPI (async)** instead of Flask. The brief lists Flask as preferred but allows FastAPI, and explicitly asks for Swagger docs "if using FastAPI." FastAPI gets automatic OpenAPI/Swagger docs and Pydantic-based request/response validation for free.
- **SQLAlchemy 2.0, async** (`AsyncSession`, `create_async_engine`, `aiosqlite` driver) over SQLite.
- **Alembic** for schema migrations, decoupled from the app's runtime engine (migrations run on the sync sqlite3 driver; the app runs on the async aiosqlite driver against the same file).
- **Pandas** for all CSV reading and cleaning.
- **slowapi** for rate limiting (a thin wrapper around the `limits` library, the standard choice for this in FastAPI).
- A single static API key for auth, not OAuth/JWT. There's no user model anywhere in this assignment, so a shared service key is the honest level of complexity for the problem.
- A plain in-memory dict for caching, not Redis. Single-process app, so a process-local cache is enough; if this ran across multiple instances a shared cache would be required instead, since each instance would otherwise cache independently and disagree.

## Project structure

```
app/
  main.py                    FastAPI app, lifespan, rate limiter wiring, error handlers
  config.py                  DB URLs, log paths, business rule constants, auth/cache/rate-limit settings
  database.py                Async engine/session setup
  models.py                  SQLAlchemy models (Customer, Policy, Claim)
  schemas.py                 Pydantic request/response schemas
  exceptions.py              Custom exception classes -> consistent error JSON
  logging_config.py          Logger setup (file + console)
  auth.py                    API key dependency
  rate_limit.py              Shared slowapi Limiter instance
  services/
    data_cleaning.py         Generic Pandas cleaning helpers
    upload_service.py        Per-entity async validation + insert logic
    business_rules.py        Payout calculation, fraud flag
    report_service.py        Raw SQL reporting queries (async)
    cache.py                 In-memory TTL cache for report endpoints
    audit.py                 Background-task audit logging for uploads
  routers/
    upload.py, claims.py, customers.py, reports.py, health.py
alembic/
  env.py                     Wired to app.models / app.config
  versions/                  Migration scripts
tests/
  test_business_rules.py     Unit tests for payout logic
  test_api.py                Integration tests (async DB, auth, uploads, claims)
requirements.txt
```

## Setup and running

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Apply the schema (Alembic is the source of truth for schema changes)
alembic upgrade head

uvicorn app.main:app --reload
```

- API root: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/docs`
- If you skip `alembic upgrade head`, the app's startup lifespan will create tables directly from the models as a dev convenience, but Alembic is what you'd actually use to evolve the schema.
- Default API key is `dev-local-api-key-change-me` (see `app/config.py`). Override with the `API_KEY` environment variable before deploying anywhere real.

Run tests:

```bash
pytest -v
```

## Authentication

`POST /upload` requires an `X-API-Key` header matching `API_KEY`. Read endpoints (`GET /claims`, `/customers/top`, `/reports/state`) are left open, since they don't mutate data and the assignment doesn't specify a permission model for read access. Only `/upload` writes to the database, so that's the one endpoint worth gating. `/health` is always open, since load balancers and orchestrators need to hit it without credentials.

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -H "X-API-Key: dev-local-api-key-change-me" \
  -F "customer_file=@customer.csv" \
  -F "policy_file=@policy.csv" \
  -F "claim_file=@claims.csv"
```

Missing or wrong key returns `401 Unauthorized`.

## Rate limiting

- Default: 60 requests/minute per client IP on most endpoints.
- `POST /upload`: 10/minute (it's the only endpoint doing real work: Pandas parsing + row validation + writes).
- `GET /health`: 300/minute (health checks are polled frequently by design).

Exceeding a limit returns `429` with `{"error": "RateLimitExceeded", "message": "..."}`. Verified live: firing 11 upload requests in under a minute returns 201 ten times and 429 on the eleventh.

## Caching

`GET /reports/state` and `GET /customers/top` are cached in-memory for 30 seconds (`REPORT_CACHE_TTL_SECONDS`), since both run aggregate queries across the full claims table. The cache is invalidated immediately after every successful `/upload`, so a write can never leave a stale cached report behind.

## Background tasks

After `/upload` responds, a background task writes a full audit record (timestamp, totals, every rejection reason) to `logs/audit.log` as a separate JSON-lines file. This happens after the response is already sent, so writing the audit trail doesn't add latency to the request. `app.log` is for live operational logs; `audit.log` is a durable record of what every upload actually did.

## API Endpoints

### `POST /upload` (requires `X-API-Key`)
Multipart form with three fields: `customer_file`, `policy_file`, `claim_file` (all `.csv`).

Processes them in dependency order: customers, then policies, then claims. Valid rows are inserted even if other rows in the same file are rejected.

```json
{
  "customers": {"total_records": 10, "inserted": 10, "rejected": 0, "errors": []},
  "policies": {"total_records": 12, "inserted": 10, "rejected": 2, "errors": ["..."]},
  "claims": {"total_records": 15, "inserted": 9, "rejected": 6, "errors": ["..."]},
  "total_records": 37,
  "inserted": 29,
  "rejected": 8,
  "errors": ["..."]
}
```

### `GET /claims/{claim_id}`
Returns the claim, its customer, its policy, the stored calculated payout, and whether the owning customer is flagged as potential fraud (more than 5 claims).

### `GET /claims`
Query params: `city`, `state`, `cause`, `date_from`, `date_to`, `min_payout`, `max_payout`, `sort_by` (`loss_date` | `loss_amount` | `final_payout` | `cause`), `order` (`asc` | `desc`), `limit` (default 50, max 500), `offset` (default 0).

Returns a paginated envelope, not a bare list, so the total count survives paging:
```json
{"items": [...], "total": 37, "limit": 50, "offset": 0}
```
`total` reflects every row matching the filters, not just the current page. Sorting and filtering are unaffected by pagination since `total` is computed from the same filtered query before `limit`/`offset` are applied.

### `GET /customers/top?n=10`
Top N customers by total payout. Raw SQL, cached.

### `GET /reports/state?basis=policy`
Per-state totals and averages. Raw SQL, cached. `basis` is `policy` (default) or `customer` — see "Key assumptions" below for why this exists as a toggle instead of a fixed choice.
```json
{"basis": "policy", "rows": [{"state": "CA", "total_claims": 4, "average_payout": 51250.0, "max_payout": 139000.0, "total_payout": 205000.0}]}
```

### `GET /health`
API status, DB connectivity check (`SELECT 1`), uptime since process start.

## Business rules implemented

1. Loss amount cannot be negative. Row rejected at upload.
2. Loss date cannot be in the future. Row rejected at upload.
3. Claim date cannot be earlier than the policy issue date. Row rejected at upload.
4. Final payout cannot exceed the policy coverage limit. Clamped, not rejected, during payout calculation.
5. Final payout cannot be negative. Clamped to 0.
6. Customers under 18 get 50% payout. Multiplier applied in `calculate_payout`.
7. Flood claims in California get an additional 10% deductible. An extra `0.10 * loss_amount` is subtracted, on top of the policy's normal deductible.
8. Customer with more than 5 claims is flagged as Potential Fraud. Computed live via a `COUNT` query, not stored as a column, so it can't drift out of sync as claims are added.
9. Duplicate claims are not inserted. Both exact duplicate rows (Pandas `drop_duplicates`) and same-ID-different-data duplicates (an in-memory seen-IDs set during row validation) are rejected, with distinct error messages for each case.
10. Policies referencing non-existent customers are rejected.

### Payout formula

```
payout = loss_amount - policy.deductible
if cause == "Flood" and policy.state == "CA":
    payout -= 0.10 * loss_amount
if customer.age < 18:
    payout *= 0.5
payout = clamp(payout, 0, policy.coverage_limit)
```

## Key assumptions (be ready to defend these)

- State is genuinely ambiguous in this schema, and that ambiguity was not resolved by guessing. A customer can live in one state and hold a policy issued in another, and the assignment doesn't say which state a "state report" means. `GET /reports/state?basis=policy|customer` lets either interpretation be checked in one call instead of requiring a guess baked into the code. Default is `policy`, because the CA flood rule (business rule 7) is written in terms of where the policy was issued, and the state report uses the same basis as the rule that touches the same data. That does not extend to business rule 7 itself: the CA flood 10% extra deductible is computed and stored into `final_payout` at ingestion time using policy state. If the correct answer turns out to be customer state, every stored `final_payout` for a flood claim would need to be recalculated, not just re-queried. That is a real limitation, not something the basis toggle covers.
- City for search filtering comes from the customer, since `claims.csv` and `policy.csv` don't carry a city field.
- Rules 4 and 5 (payout limits) are treated as calculation constraints (clamped), not rejection rules. An over-limit claim is still valid, it just gets capped at the payout stage. Rules 1 through 3 and 9 through 10 reject the row outright because the record itself is invalid.
- Partial success on `/upload`. Valid rows are inserted even when other rows in the same file fail.
- Duplicate detection has two layers: exact duplicate rows and duplicate IDs with differing data, with different error messages for each.
- Age must be between 0 and 130 to count as valid, enforced both in application code and as a database CHECK constraint (see "Database design" below).
- Auth only gates the write path, not reads. See the Authentication section above for the reasoning.
- Cache TTL is 30 seconds but invalidated on every write, so it never serves stale data after an upload. The TTL only matters between uploads, to avoid recomputing the same aggregate query on every request.

## Database design

Validation is not only enforced in application code. The schema itself rejects bad data independently of the API:

- CHECK constraints: `customers.age` between 0 and 130, `policies.coverage_limit > 0`, `policies.deductible >= 0`, `claims.loss_amount >= 0`, `claims.final_payout >= 0`. A direct SQL insert that violates any of these fails at the database layer, not just the API layer. Verified directly: inserting a claim with a negative `loss_amount` through the ORM, bypassing the application's own validation logic, raises `IntegrityError`.
- Foreign keys are actually enforced, which took an explicit fix. SQLite declares foreign keys in the schema but does not enforce them by default. A raw insert can reference a nonexistent parent row and SQLite accepts it silently unless `PRAGMA foreign_keys=ON` is set on every connection. This is set in `app/database.py` via a `connect` event listener. Verified directly, before and after: a raw SQL insert of a child row referencing a nonexistent parent succeeded silently before the pragma was added, and raises `IntegrityError` after.
- Indexes on every column actually used in a filter, sort, or join: `policies.customer_id`, `policies.state`, `claims.policy_id`, `claims.loss_date`, `claims.cause`, `claims.final_payout`, `customers.city`. SQLite does not automatically index foreign key columns, so `policies.customer_id` and `claims.policy_id` needed explicit indexes for the joins in every claims query to not be full table scans.
- What this doesn't cover: cross-table rules, such as a claim's loss date not being earlier than its policy's issue date, can't be expressed as a single-table CHECK constraint in SQLite. That rule stays in application code (`upload_service.py`) and would need a trigger to enforce at the database layer too, which wasn't worth the added complexity here. It's enforced at one layer instead of two, and that's a real, stated tradeoff, not an oversight.

## Logging

`logs/app.log`: every request (method, path, status, duration) via middleware, upload summaries, all handled errors at WARNING, unhandled exceptions at ERROR with stack trace.

`logs/audit.log`: one JSON line per upload with full detail on what was inserted or rejected and why.

Deliberately not logged: request bodies, query params, the API key header, customer names or ages. Anything that could carry PII or secrets.

## Error handling

All errors return `{"error": "<Type>", "message": "<detail>"}`:
- `401 Unauthorized`: missing or invalid API key on `/upload`.
- `404 NotFound`: claim doesn't exist.
- `422 ValidationError`: bad query params, FastAPI request validation failures.
- `400 BadRequest`: malformed upload request, for example wrong file type.
- `429 RateLimitExceeded`: too many requests from one client.
- `500 InternalServerError`: unhandled exceptions, caught by a global handler so nothing leaks a raw stack trace.

## Database migrations

```bash
alembic upgrade head                                   # apply migrations
alembic revision --autogenerate -m "description"       # generate a new one after changing models.py
alembic downgrade -1                                    # roll back one step
```

`alembic/env.py` imports `app.models` and `app.config.DATABASE_URL` directly, so the migration schema and the app's ORM models can never silently drift apart. There is exactly one definition of the schema, in `models.py`, and Alembic diffs against it.

There are two real migrations here, not one:
1. `7cb52c44501f`: initial schema (three tables, foreign keys, primary keys).
2. `df8beb210e38`: adds the CHECK constraints and indexes described above.

The second migration exists because `alembic revision --autogenerate` does not reliably detect CHECK constraint changes on an existing table, which is a known limitation of Alembic's autogenerate, not specific to this schema. It caught all seven new indexes automatically but missed all five CHECK constraints entirely. Those were added by hand, using `op.batch_alter_table(...)`, which SQLite requires for `ALTER TABLE` operations it can't do directly (SQLite handles this by rebuilding the table under the hood). The full upgrade and downgrade cycle for this migration was tested directly: `alembic upgrade head` applies both the constraints and indexes, `alembic downgrade -1` removes both cleanly, and `alembic upgrade head` again restores them, confirmed each time by inspecting `sqlite_master` directly rather than assuming the migration did what it claimed.

## Known limitations and what I would do with more time

- The static API key has no rotation or expiry mechanism. Fine for this assignment, not for production. Would move to per-client keys stored hashed in the DB, or real OAuth if there were an actual user base.
- The in-memory cache and rate limiter state are process-local. Running this behind multiple worker processes (for example `uvicorn --workers 4`) would mean each worker has its own independent cache and its own independent rate-limit counters, which is a real correctness gap at scale. A shared Redis-backed cache and limiter would be needed there.
- `/upload` re-reads the full customer and policy tables into memory for foreign-key lookups on every call. Fine at this data size, would move to targeted queries or a bulk upsert for large files.
- Rate limiting and caching were verified manually with live curl runs (shown working: 10 uploads succeed, the 11th in the same minute returns 429) rather than with automated tests. Would add explicit automated tests for both before calling this fully production ready.
- The `basis` toggle on `/reports/state` resolves the ambiguity for reporting, but not for the CA flood rule itself, which is baked into stored `final_payout` values at ingestion time using policy state. Switching that basis would mean a recomputation pass over existing claims, not a query change. This is stated plainly above rather than implied to be fully solved.
- Cross-table validation rules (claim date vs. policy issue date) are enforced in application code only, not as a database-level trigger. Single-table CHECK constraints cover everything that can be expressed within one table; anything that needs to compare across tables currently relies on the application layer alone.
