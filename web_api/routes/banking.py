from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.banking.workspace import ContactInput, DealInput, TaskInput, RecordConflict, BankingRecord, activities, save_record, workspace
from modules.banking.valuation import DcfInputs, calculate_dcf
from modules.banking.comparables import CompsInputs, calculate_comps
from modules.banking.workspace import ValuationInput
from web_api.auth import require_api_key
from web_api.routes.clients import get_db
from web_api.view_model import attach_meta

router = APIRouter(prefix="/api/banking", tags=["Advisory"], dependencies=[Depends(require_api_key)])


def response(payload: dict, route: str) -> dict:
    return attach_meta(payload, route="/api/banking" + route, source="local operator records", warnings=[])


def save(db, kind, payload, record_id=None):
    try:
        return response({kind[:-1]: save_record(db, kind, payload, record_id)}, "/" + kind)
    except RecordConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "A matching record already exists for this client.") from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        db.rollback()
        detail = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"]} for item in exc.errors()] if isinstance(exc, ValidationError) else str(exc)
        raise HTTPException(422, detail) from exc


@router.get("/workspace")
def read_workspace(db: Session = Depends(get_db)):
    return response(workspace(db), "/workspace")


@router.post("/deals", status_code=201)
def create_deal(payload: DealInput, db: Session = Depends(get_db)):
    return save(db, "deals", payload.model_dump(mode="json"))


@router.post("/contacts", status_code=201)
def create_contact(payload: ContactInput, db: Session = Depends(get_db)):
    return save(db, "contacts", payload.model_dump(mode="json"))


@router.post("/tasks", status_code=201)
def create_task(payload: TaskInput, db: Session = Depends(get_db)):
    return save(db, "tasks", payload.model_dump(mode="json"))


@router.patch("/{kind}/{record_id}")
def update_record(kind: Literal["deals", "contacts", "tasks"], record_id: str, payload: dict, db: Session = Depends(get_db)):
    return save(db, kind, payload, record_id)


@router.get("/deals/{record_id}/activity")
def deal_activity(record_id: str, db: Session = Depends(get_db)):
    row = db.get(BankingRecord, record_id)
    if row is None or row.kind != "deals":
        raise HTTPException(404, "Deal not found.")
    return response({"activities": activities(db, record_id)}, "/deals/{id}/activity")


@router.get("/export")
def export_workspace(db: Session = Depends(get_db)):
    return response({**workspace(db), "activities": activities(db)}, "/export")


@router.post("/valuation/dcf")
def value_dcf(payload: DcfInputs):
    try:
        result = calculate_dcf(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return attach_meta(result, route="/api/banking/valuation/dcf", source="user-supplied valuation assumptions", warnings=result["warnings"])


@router.post("/valuation/comps")
def value_comps(payload: CompsInputs):
    try:
        result = calculate_comps(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return attach_meta(result, route="/api/banking/valuation/comps", source="user-supplied comparable assumptions", warnings=result["warnings"])


@router.post("/valuations", status_code=201)
def create_valuation(payload: ValuationInput, db: Session = Depends(get_db)):
    return save(db, "valuations", payload.model_dump(mode="json"))
