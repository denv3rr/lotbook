"""Product identity and environment-variable names.

Runtime code should read LOTBOOK_* names through getenv() so a leftover
CLEAR_* value from an older checkout still works. Do not use this module
for terminal-clear helpers or collection .clear() calls.
"""
from __future__ import annotations

import os

PRODUCT_NAME = "Lotbook"
COMMAND_NAME = "lotbook"
WEB_API_KEY_ENV = "LOTBOOK_WEB_API_KEY"
LEGACY_WEB_API_KEY_ENV = "CLEAR_WEB_API_KEY"


def getenv(name: str, default: str = "") -> str:
    """Prefer the current LOTBOOK_* name, then the legacy CLEAR_* suffix."""
    value = os.getenv(name)
    if value:
        return value
    if name.startswith("LOTBOOK_"):
        legacy = os.getenv("CLEAR_" + name[len("LOTBOOK_") :])
        if legacy:
            return legacy
    return default
