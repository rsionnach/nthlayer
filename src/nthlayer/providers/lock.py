"""
Re-export shim — canonical source is nthlayer_common.providers.lock.

This shim maintains backward compatibility during the ecosystem migration.
"""

from nthlayer_common.providers.lock import (  # noqa: F401
    DEFAULT_LOCK_PATH,
    ProviderLock,
    load_lock,
    save_lock,
)

__all__ = [
    "ProviderLock",
    "DEFAULT_LOCK_PATH",
    "load_lock",
    "save_lock",
]
