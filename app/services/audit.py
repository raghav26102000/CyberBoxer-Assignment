"""
Runs as a FastAPI background task after /upload responds, so the client
doesn't wait on disk I/O for something that isn't needed to answer the
request. Writes one JSON line per upload to a separate audit log --
kept apart from app.log so operational logs and audit trail don't mix.
"""
import json
import os
from datetime import datetime, timezone
from app.config import AUDIT_LOG_FILE, LOG_DIR


def write_upload_audit_record(result: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_records": result["total_records"],
        "inserted": result["inserted"],
        "rejected": result["rejected"],
        "error_count": len(result["errors"]),
        # Full error text (not just counts) so the audit trail is enough
        # to investigate a bad upload after the fact without re-running it.
        "errors": result["errors"],
    }
    with open(AUDIT_LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
