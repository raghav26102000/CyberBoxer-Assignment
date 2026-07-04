"""
Central configuration. Kept as plain constants instead of a full settings
library (e.g. pydantic-settings) since the assignment scope doesn't need
multiple environments -- documented as an assumption in the README.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sync URL is used by Alembic (migration tooling doesn't need async).
# Async URL is used by the running application.
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/claims.db")
ASYNC_DATABASE_URL = os.environ.get(
    "ASYNC_DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/claims.db"
)

LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")
AUDIT_LOG_FILE = os.path.join(LOG_DIR, "audit.log")

# Business rule constants (kept in one place so they're easy to find/change)
MINOR_AGE_THRESHOLD = 18
MINOR_PAYOUT_MULTIPLIER = 0.5
CA_FLOOD_EXTRA_DEDUCTIBLE_RATE = 0.10
FRAUD_CLAIM_COUNT_THRESHOLD = 5

# Auth: a single static API key checked against the X-API-Key header.
# Not JWT/OAuth on purpose -- there's no user model in this assignment,
# so a shared service key is the honest level of complexity for the
# problem, not a toy OAuth flow bolted on for show.
API_KEY = os.environ.get("API_KEY", "dev-local-api-key-change-me")
API_KEY_HEADER_NAME = "X-API-Key"

# Caching: simple in-memory TTL cache for the two report endpoints,
# which run aggregate queries over the full claims table. Invalidated
# immediately whenever /upload inserts new data, so it can never serve
# stale numbers after a write.
REPORT_CACHE_TTL_SECONDS = int(os.environ.get("REPORT_CACHE_TTL_SECONDS", "30"))

# Rate limiting (slowapi / limits library syntax: "<count>/<period>")
DEFAULT_RATE_LIMIT = os.environ.get("DEFAULT_RATE_LIMIT", "60/minute")
UPLOAD_RATE_LIMIT = os.environ.get("UPLOAD_RATE_LIMIT", "10/minute")
