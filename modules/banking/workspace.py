"""Client-linked advisory records with revision checks and change history."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UniqueConstraint, update
from sqlalchemy.orm import Session

from core.database import Base
from core.models import Client


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decimal_input(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("Enter a finite number.")
    if len(str(value)) > 64:
        raise ValueError("Number is too long.")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Enter a finite number.") from exc
    if not number.is_finite() or abs(number) > Decimal("1e18"):
        raise ValueError("Enter a finite number no larger than 1e18.")
    if number.as_tuple().exponent < -12:
        raise ValueError("Use no more than twelve fractional decimal places.")
    return number


Amount = Annotated[Decimal, BeforeValidator(decimal_input)]
Text = Annotated[str, Field(min_length=1, max_length=160)]


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_id: Text
    owner: Text
    source_note: str = Field(min_length=1, max_length=4000)


class DealInput(RecordInput):
    name: Text
    deal_type: Literal["sell_side", "buy_side", "capital_raise", "debt_advisory", "restructuring"]
    stage: Literal["prospect", "pitch", "mandated", "diligence", "negotiation", "closed", "lost", "on_hold"] = "prospect"
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    expected_value: Amount | None = Field(default=None, ge=0)
    fee_bps: Amount | None = Field(default=None, ge=0, le=10000)
    close_probability: Amount | None = Field(default=None, ge=0, le=1)
    target_close: date | None = None
    next_action: str = Field(default="", max_length=4000)


class ContactInput(RecordInput):
    name: Text
    title: str = Field(default="", max_length=160)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=4000)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        if value and (value.count("@") != 1 or any(c.isspace() for c in value) or not all(value.split("@"))):
            raise ValueError("Enter a valid email address or leave it blank.")
        return value


class TaskInput(RecordInput):
    title: Text
    deal_id: str | None = Field(default=None, max_length=80)
    due_date: date | None = None
    status: Literal["open", "in_progress", "blocked", "completed"] = "open"
    category: Literal["follow_up", "diligence", "meeting", "deliverable"] = "follow_up"
    notes: str = Field(default="", max_length=4000)


class ValuationInput(RecordInput):
    name: Text
    model_kind: Literal["dcf", "comps"]
    inputs: dict
    deal_id: str | None = Field(default=None, max_length=80)
    supersedes_id: str | None = Field(default=None, max_length=80)


SCHEMAS = {"deals": DealInput, "contacts": ContactInput, "tasks": TaskInput, "valuations": ValuationInput}


class BankingRecord(Base):
    __tablename__ = "banking_records"
    id = Column(String, primary_key=True)
    client_pk = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    identity_key = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("client_pk", "kind", "identity_key", name="uq_banking_identity"),)


class BankingActivity(Base):
    __tablename__ = "banking_activity"
    id = Column(String, primary_key=True)
    record_id = Column(String, ForeignKey("banking_records.id", ondelete="RESTRICT"), nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    action = Column(String, nullable=False)
    created_at = Column(String, nullable=False)
    changes = Column(JSON, nullable=False)


class RecordConflict(ValueError):
    """An edit was based on a stale revision."""


def present(row: BankingRecord) -> dict:
    return {**row.payload, "id": row.id, "revision": row.revision, "created_at": row.created_at, "updated_at": row.updated_at}


def identity(kind: str, data: dict, record_id: str) -> str:
    if kind in ("tasks", "valuations"):
        return record_id
    return " ".join(data["name"].casefold().split()) + ("|" + data["email"].casefold() if kind == "contacts" else "")


def save_record(db: Session, kind: str, body: dict, record_id: str | None = None) -> dict:
    schema = SCHEMAS[kind]
    if kind == "valuations" and record_id:
        raise ValueError("Saved valuations are immutable. Save a new version instead.")
    row = db.get(BankingRecord, record_id) if record_id else None
    if record_id and (row is None or row.kind != kind):
        raise LookupError("Record not found.")
    before = dict(row.payload) if row else {}
    if row:
        revision = body.get("expected_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision != row.revision:
            raise RecordConflict("This record changed. Reload the workspace before editing again.")
        if "client_id" in body:
            raise ValueError("A saved record cannot be moved to another client.")
        changes = {key: value for key, value in body.items() if key != "expected_revision"}
        data = schema.model_validate({**before, **changes}).model_dump(mode="json")
    else:
        data = schema.model_validate(body).model_dump(mode="json")
    client = db.query(Client).filter(Client.client_uid == data["client_id"]).one_or_none()
    if client is None:
        raise LookupError("Choose an existing client.")
    if kind in ("tasks", "valuations") and data.get("deal_id"):
        deal = db.get(BankingRecord, data["deal_id"])
        if deal is None or deal.kind != "deals" or deal.client_pk != client.id:
            raise ValueError("The linked deal must belong to the same client.")
    if kind == "valuations":
        from modules.banking.valuation import DcfInputs, calculate_dcf
        from modules.banking.comparables import CompsInputs, calculate_comps
        if data.get("supersedes_id"):
            prior = db.get(BankingRecord, data["supersedes_id"])
            if prior is None or prior.kind != kind or prior.client_pk != client.id or prior.payload["model_kind"] != data["model_kind"]:
                raise ValueError("The prior version must be a valuation of this type for the same client.")
        calculate, model = (calculate_dcf, DcfInputs) if data["model_kind"] == "dcf" else (calculate_comps, CompsInputs)
        data["result"] = calculate(model.model_validate(data["inputs"]))
    stamp = utc_now()
    entity_id = record_id or str(uuid4())
    key = identity(kind, data, entity_id)
    if row:
        result = db.execute(update(BankingRecord).where(BankingRecord.id == entity_id, BankingRecord.revision == revision).values(
            payload=data, identity_key=key, revision=revision + 1, updated_at=stamp), execution_options={"synchronize_session": False})
        if result.rowcount != 1:
            raise RecordConflict("This record changed. Reload the workspace before editing again.")
    else:
        row = BankingRecord(id=entity_id, client_pk=client.id, kind=kind, identity_key=key, payload=data, revision=1, created_at=stamp, updated_at=stamp)
        db.add(row)
        db.flush()
    db.add(BankingActivity(id=str(uuid4()), record_id=entity_id, entity_type=kind, action="updated" if record_id else "created", created_at=stamp,
        changes={key: {"before": before.get(key), "after": value} for key, value in data.items() if key not in before or before[key] != value}))
    db.commit()
    db.refresh(row)
    return present(row)


def workspace(db: Session) -> dict:
    with localcontext() as context:
        context.prec = 128
        return _workspace(db)


def _workspace(db: Session) -> dict:
    from modules.client_store import DbClientStore
    from modules.view_models import list_clients
    groups = {kind: [] for kind in SCHEMAS}
    for row in db.query(BankingRecord).order_by(BankingRecord.updated_at.desc(), BankingRecord.id).all():
        groups[row.kind].append(present(row))
    active = [deal for deal in groups["deals"] if deal["stage"] not in ("closed", "lost", "on_hold")]
    currencies = []
    for currency in sorted({deal["currency"] for deal in active}):
        rows = [deal for deal in active if deal["currency"] == currency]
        values, fees, weighted = [], [], []
        for deal in rows:
            if deal["expected_value"] is not None:
                value = Decimal(deal["expected_value"])
                values.append(value)
                if deal["fee_bps"] is not None:
                    fee = value * Decimal(deal["fee_bps"]) / 10000
                    fees.append(fee)
                    if deal["close_probability"] is not None:
                        weighted.append(fee * Decimal(deal["close_probability"]))
        currencies.append({"currency": currency, "deals": len(rows), "pipeline_value": str(sum(values)) if values else None,
            "expected_fees": str(sum(fees)) if fees else None, "weighted_fees": str(sum(weighted)) if weighted else None,
            "value_coverage": len(values), "fee_coverage": len(fees), "weighted_coverage": len(weighted)})
    open_tasks = [task for task in groups["tasks"] if task["status"] != "completed"]
    today = datetime.now(timezone.utc).date().isoformat()
    return {"schema_version": "banking.v1", "clients": list_clients(DbClientStore(db).fetch_all_clients()), **groups,
        "summary": {"active_deals": len(active), "open_tasks": len(open_tasks), "overdue_tasks": sum(bool(task["due_date"] and task["due_date"] < today) for task in open_tasks), "by_currency": currencies},
        "methodology": {"source": "Operator-entered local records; source notes are not independently verified.", "window": "Current records; overdue uses UTC calendar date.", "pipeline": "Excludes closed, lost and on-hold records; sums available values within each currency only.", "fees": "expected_value * fee_bps / 10000; weighted fees multiply by operator close_probability. Partial coverage is reported. These are estimates, not booked revenue."}}


def activities(db: Session, record_id: str | None = None) -> list[dict]:
    query = db.query(BankingActivity)
    if record_id:
        query = query.filter(BankingActivity.record_id == record_id)
    return [{"id": row.id, "record_id": row.record_id, "entity_type": row.entity_type, "action": row.action, "created_at": row.created_at, "changes": row.changes} for row in query.order_by(BankingActivity.created_at.desc()).all()]
