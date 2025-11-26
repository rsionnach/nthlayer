from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class JobMessage:
    job_id: str
    job_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    requested_by: str | None = None

    def to_message_body(self) -> str:
        data = asdict(self)
        return json.dumps({k: v for k, v in data.items() if v is not None}, separators=(",", ":"))
