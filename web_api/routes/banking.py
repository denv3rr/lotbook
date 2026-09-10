from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.banking.workspace import (
    ApprovalInput,
    BidInput,
    ContactInput,
    DealInput,
    DocumentInput,
    IntakeInput,
    PartyInput,
    RecordConflict,
    BankingRecord,
    TaskInput,
    ValuationInput,
    activities,
    save_record,
    workspace,
)
from modules.banking.valuation import DcfInputs, calculate_dcf
from modules.banking.comparables import CompsInputs, calculate_comps
from modules.banking.screening import CapitalStructureInputs, DebtScheduleInputs, StatementInputs, WaccInputs, calculate_capital_structure, calculate_debt_schedule, calculate_statements, calculate_wacc
from modules.banking.deals_math import LboInputs, MergerInputs, PrecedentInputs, calculate_lbo, calculate_merger, calculate_precedent
from modules.banking.instruments import BondInputs, OptionInputs, calculate_bond, calculate_option
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


@router.post("/intake", status_code=201)
def create_intake(payload: IntakeInput, db: Session = Depends(get_db)):
    return save(db, "intake", payload.model_dump(mode="json"))


@router.post("/parties", status_code=201)
def create_party(payload: PartyInput, db: Session = Depends(get_db)):
    return save(db, "parties", payload.model_dump(mode="json"))


@router.post("/bids", status_code=201)
def create_bid(payload: BidInput, db: Session = Depends(get_db)):
    return save(db, "bids", payload.model_dump(mode="json"))


@router.post("/documents", status_code=201)
def create_document(payload: DocumentInput, db: Session = Depends(get_db)):
    return save(db, "documents", payload.model_dump(mode="json"))


@router.post("/approvals", status_code=201)
def create_approval(payload: ApprovalInput, db: Session = Depends(get_db)):
    return save(db, "approvals", payload.model_dump(mode="json"))


@router.patch("/{kind}/{record_id}")
def update_record(kind: Literal["deals", "contacts", "tasks", "intake", "parties", "bids", "documents", "approvals"], record_id: str, payload: dict, db: Session = Depends(get_db)):
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


def calculate(payload, function, route: str, source: str):
    try:
        result = function(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return attach_meta(result, route=route, source=source, warnings=result.get("warnings") or [])


@router.post("/valuation/wacc")
def value_wacc(payload: WaccInputs):
    return calculate(payload, calculate_wacc, "/api/banking/valuation/wacc", "user-supplied capital-cost assumptions")


@router.post("/valuation/capital-structure")
def value_structure(payload: CapitalStructureInputs):
    return calculate(payload, calculate_capital_structure, "/api/banking/valuation/capital-structure", "user-supplied capital-structure assumptions")


@router.post("/valuation/debt-schedule")
def value_debt(payload: DebtScheduleInputs):
    return calculate(payload, calculate_debt_schedule, "/api/banking/valuation/debt-schedule", "user-supplied debt-schedule assumptions")


@router.post("/valuation/statements")
def value_statements(payload: StatementInputs):
    return calculate(payload, calculate_statements, "/api/banking/valuation/statements", "user-supplied statement assumptions")


@router.post("/valuation/merger")
def value_merger(payload: MergerInputs):
    return calculate(payload, calculate_merger, "/api/banking/valuation/merger", "user-supplied merger assumptions")


@router.post("/valuation/lbo")
def value_lbo(payload: LboInputs):
    return calculate(payload, calculate_lbo, "/api/banking/valuation/lbo", "user-supplied LBO assumptions")


@router.post("/valuation/precedent")
def value_precedent(payload: PrecedentInputs):
    return calculate(payload, calculate_precedent, "/api/banking/valuation/precedent", "user-supplied precedent assumptions")


@router.post("/valuation/bond")
def value_bond(payload: BondInputs):
    return calculate(payload, calculate_bond, "/api/banking/valuation/bond", "user-supplied bond assumptions")


@router.post("/valuation/option")
def value_option(payload: OptionInputs):
    return calculate(payload, calculate_option, "/api/banking/valuation/option", "user-supplied option assumptions")


@router.post("/valuations", status_code=201)
def create_valuation(payload: ValuationInput, db: Session = Depends(get_db)):
    return save(db, "valuations", payload.model_dump(mode="json"))
