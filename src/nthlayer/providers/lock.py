from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

DEFAULT_LOCK_PATH = Path("providers.lock")


@dataclass
class ProviderLock:
    providers: Dict[str, str] = field(default_factory=dict)

    def set(self, name: str, version: str) -> None:
        self.providers[name] = version

    def get(self, name: str) -> str | None:
        return self.providers.get(name)


def load_lock(path: Path | None = None) -> ProviderLock:
    lock_path = path or DEFAULT_LOCK_PATH
    if not lock_path.exists():
        return ProviderLock()
    data = json.loads(lock_path.read_text())
    providers = data.get("providers", {})
    return ProviderLock(providers=dict(providers))


def save_lock(lock: ProviderLock, path: Path | None = None) -> None:
    lock_path = path or DEFAULT_LOCK_PATH
    payload = {"providers": lock.providers}
    lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
