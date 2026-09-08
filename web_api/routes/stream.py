from __future__ import annotations

import asyncio
import errno
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from modules.market_data.trackers import GlobalTrackers
from web_api.auth import require_websocket_key
from web_api.view_model import attach_meta, validate_payload

router = APIRouter()


def _is_expected_disconnect_error(exc: BaseException) -> bool:
    if isinstance(exc, (WebSocketDisconnect, ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError):
        if exc.errno in {errno.EPIPE, errno.EBADF, errno.ECONNRESET, 10053, 10054}:
            return True
        message = str(exc).lower()
        return any(token in message for token in ("broken pipe", "connection reset", "closed"))
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "close message has been sent",
                "websocket is not connected",
                "cannot call send once a close message has been sent",
            )
        )
    return False


@router.websocket("/ws/trackers")
async def trackers_stream(websocket: WebSocket, mode: Optional[str] = None, interval: int = 5):
    ok, subprotocol = require_websocket_key(websocket)
    if not ok:
        await websocket.close(code=1008, reason="Invalid API key")
        return
    await websocket.accept(subprotocol=subprotocol)
    trackers = GlobalTrackers()
    stream_mode = mode or "combined"
    stream_interval = max(1, min(int(interval or 5), 60))
    try:
        while True:
            payload = await run_in_threadpool(trackers.get_snapshot, mode=stream_mode)
            warnings = list(payload.get("warnings", []) or [])
            warnings = validate_payload(
                payload,
                required_keys=("mode", "count", "points"),
                non_empty_keys=("points",),
                warnings=warnings,
            )
            attach_meta(
                payload,
                route="/ws/trackers",
                source="trackers_stream",
                warnings=warnings,
            )
            await websocket.send_json(payload)
            await asyncio.sleep(stream_interval)
    except WebSocketDisconnect:
        return
    except (OSError, RuntimeError) as exc:
        if _is_expected_disconnect_error(exc):
            return
        raise
