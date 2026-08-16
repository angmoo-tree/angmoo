"""Print one privacy-safe application runtime status JSON document.

The host launcher invokes this inside the backend container. It intentionally
does not accept secrets or emit host/container details.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.db import SessionLocal
from app.core.redaction import sanitize_support_bundle_metadata
from app.domains.runtime.public import (
    ReadApplicationRuntimeStatus,
    SqlAlchemyApplicationRuntimeProbe,
    runtime_status_read,
)


def main() -> int:
    with SessionLocal() as db:
        status = ReadApplicationRuntimeStatus(
            SqlAlchemyApplicationRuntimeProbe(db)
        ).execute()
        payload = runtime_status_read(status).model_dump(mode="json")
    safe_payload = sanitize_support_bundle_metadata(payload)
    print(json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
