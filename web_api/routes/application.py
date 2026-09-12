from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from utils.stack_control import own_control
from web_api.auth import header_confirmed, require_api_key
from web_api.view_model import attach_meta

router = APIRouter(prefix="/api/application", tags=["Application"], dependencies=[Depends(require_api_key)])


class ShutdownRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool


@router.get("/status")
def application_status(request: Request):
    control = own_control()
    available = bool(control and control[1]["processes"].get("web")) and callable(getattr(request.app.state, "request_shutdown", None))
    return attach_meta({"shutdown_available": available, "message": "Ready to close this Lotbook stack." if available else "Restart using the Lotbook launcher without --reload to enable safe app shutdown."}, route="/api/application/status", source="launcher")


@router.post("/shutdown", status_code=202)
def shutdown(payload: ShutdownRequest, request: Request, background: BackgroundTasks):
    if not payload.confirm:
        raise HTTPException(400, "Explicit confirmation is required.")
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "App shutdown is available only on the local computer.")
    if not header_confirmed(request.headers, "x-lotbook-shutdown"):
        raise HTTPException(403, "The application shutdown header is required.")
    control = own_control()
    callback = getattr(request.app.state, "request_shutdown", None)
    if control is None or not control[1]["processes"].get("web") or not callable(callback):
        raise HTTPException(409, "This API was not started as a managed Lotbook stack. Restart using the Lotbook launcher without --reload.")
    origin = request.headers.get("origin")
    expected = urlsplit(control[1]["ui_origin"])
    if origin and origin not in (control[1]["ui_origin"], f"http://localhost:{expected.port}"):
        raise HTTPException(403, "Shutdown must come from this Lotbook dashboard.")
    background.add_task(callback)
    return attach_meta({"status": "stopping", "message": "Shutdown requested. Lotbook will finish active API work, then stop its UI process tree. You can close this browser tab."}, route="/api/application/shutdown", source="launcher")
