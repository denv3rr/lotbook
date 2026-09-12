from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import Header, HTTPException
from fastapi import WebSocket

from utils.identity import WEB_API_KEY_ENV, getenv

LOGGER = logging.getLogger(__name__)
_UNSET_KEY_WARNED = False
_WS_KEY_PREFIXES = ("lotbook-key.", "clear-key.")


def _expected_api_key() -> str:
    global _UNSET_KEY_WARNED
    expected = getenv(WEB_API_KEY_ENV)
    if expected:
        return expected
    if not _UNSET_KEY_WARNED:
        LOGGER.warning(
            "%s is unset; API and WebSocket auth are open. "
            "Set a key for any shared or public deployment.",
            WEB_API_KEY_ENV,
        )
        _UNSET_KEY_WARNED = True
    return ""


def _keys_match(provided: Optional[str], expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = _expected_api_key()
    if not expected:
        return
    if not _keys_match(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


def require_websocket_key(websocket: WebSocket) -> tuple[bool, Optional[str]]:
    expected = _expected_api_key()
    if not expected:
        return True, None
    api_key = websocket.headers.get("x-api-key")
    if _keys_match(api_key, expected):
        return True, None
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    for proto in protocols.split(","):
        candidate = proto.strip()
        for prefix in _WS_KEY_PREFIXES:
            if candidate.startswith(prefix) and _keys_match(candidate[len(prefix):].strip(), expected):
                return True, candidate
    return False, None


def header_confirmed(headers, name: str) -> bool:
    """Accept the current X-Lotbook-* confirm header or the legacy X-Clear-* name."""
    legacy = name.replace("x-lotbook-", "x-clear-")
    return headers.get(name) == "confirm" or headers.get(legacy) == "confirm"
