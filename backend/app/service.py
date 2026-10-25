"""Application state machine and tool logic. Every accepted change runs in one DB transaction:
claim operation id, lock the row, validate all fields before writing any, bump revision,
write change events (outbox), commit. Notification to listeners happens after commit by SSE polling the events table."""
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from . import formschema as fs
from .db import AppEvent, Application, Operation, now

MAX_OTP_ATTEMPTS = 5


class Conflict(Exception):
    def __init__(self, message: str, extra: dict | None = None):
        self.message, self.extra = message, extra or {}


class NotFound(Exception):
    pass


def create_application(db: Session, tenant: str, phone: str, language: str, variant: str | None, created_by: str,
                       name: str | None = None) -> Application:
    app = Application(id=str(uuid.uuid4()), tenant_id=tenant, schema_version=fs.SCHEMA_VERSION, variant=variant,
                      phone=phone, call_language=language, data={}, created_by=created_by)
    if variant:
        app.data = {"variant": {"value": variant, "status": "captured", "source": "operator", "rev": 0}}
    if name:  # an operator-typed name is only a hint; the candidate still confirms it on the call
        app.data = {**app.data, "candidate_name": {"value": name[:100], "status": "captured", "source": "operator", "rev": 0}}
    db.add(app)
    db.flush()
    _event(db, app, "session_created", {})
    db.commit()
    return app


def load(db: Session, app_id: str, tenant: str, lock: bool = False) -> Application:
    q = select(Application).where(Application.id == app_id, Application.tenant_id == tenant)
    if lock:
        q = q.with_for_update()
    app = db.execute(q).scalar_one_or_none()
    if not app:
        raise NotFound()
    return app


def _event(db: Session, app: Application, type_: str, payload: dict):
    db.add(AppEvent(application_id=app.id, revision=app.revision, type=type_, payload=payload))


def _recompute_state(app: Application) -> str | None:
    """Return the new state if it changed. Never moves out of submitted."""
    if app.state == "submitted":
        return None
    new = "draft" if not app.data else "collecting"
    if app.data and ready_blockers(app) == []:
        new = "ready_for_submission"
    if new != app.state:
        app.state = new
        return new
    return None


def ready_blockers(app: Application) -> list[str]:
    b = []
    if not app.consent_given:
        b.append("consent")
    if not app.otp_verified:
        b.append("otp")
    b += fs.missing_fields(app.data, app.variant)
    b += [f"confirm:{x}" for x in fs.unconfirmed_fields(app.data, app.variant)]
    if app.data.get("declaration_accepted", {}).get("value") is not True:
        if "declaration_accepted" not in b:
            b.append("declaration_accepted")
    return b


def snapshot(app: Application) -> dict:
    derived = fs.compute_derived(app.data)
    return {
        "id": app.id, "schema_version": app.schema_version, "variant": app.variant, "state": app.state,
        "call_status": app.call_status, "delivery_status": app.delivery_status, "revision": app.revision,
        "data": app.data, "derived": derived, "missing": fs.missing_fields(app.data, app.variant),
        "unconfirmed": fs.unconfirmed_fields(app.data, app.variant), "warnings": fs.warnings_for(app.data),
        "consent_given": app.consent_given, "otp_verified": app.otp_verified, "help_requested": app.help_requested,
        "call_language": app.call_language, "language_locked": app.language_locked, "phone": app.phone,
        "created_at": app.created_at.isoformat(), "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
    }


def next_step(app: Application) -> tuple[str, str]:
    """(next_action, guidance for the voice agent). Ordered so the agent only asks what is still needed."""
    if app.state == "submitted":
        return "finish_call", "The application is already submitted. Thank the candidate and end the call."
    if not app.consent_given:
        return "ask_consent", "Ask permission to fill the form and take the information. Call record_consent only after a clear yes."
    if not app.otp_verified:
        return "verify_otp", "Ask the candidate for the code sent to this number, then call verify_otp."
    missing = fs.missing_fields(app.data, app.variant)
    if missing:
        top = missing[0]
        return "ask_missing", f"Ask next for: {fs.label(top)} ({top}). Accept several details in one answer and save each."
    uncon = fs.unconfirmed_fields(app.data, app.variant)
    if uncon:
        return "confirm_values", f"Read back and get a yes for: {', '.join(uncon[:3])}. Save again with confirmed true only after an explicit yes."
    if app.data.get("declaration_accepted", {}).get("value") is not True:
        return "ask_declaration", "Read the declaration that the information is correct to the best of the candidate's knowledge, then save declaration_accepted after an explicit yes."
    return "submit", "Everything is collected. Call submit_application, and say it is submitted only after it succeeds."


def _result(app: Application, saved: bool, accepted: list[str], errors: list[dict], extra: dict | None = None) -> dict:
    action, guidance = next_step(app)
    missing = fs.missing_fields(app.data, app.variant)
    r = {
        "saved": saved, "application_revision": app.revision, "state": app.state,
        "accepted_fields": accepted, "validation_errors": errors,
        "missing_fields": missing[:5], "missing_count": len(missing),
        "warnings": fs.warnings_for(app.data), "next_action": action, "guidance": guidance,
    }
    if errors:
        r["agent_message"] = "Not saved: " + "; ".join(f"{e['field']}: {e['message']}" for e in errors[:3]) + " Ask the candidate again for only that detail."
    elif accepted:
        r["agent_message"] = f"Saved {', '.join(accepted)}. {guidance}"
    else:
        r["agent_message"] = guidance
    if extra:
        r.update(extra)
    return r


def _claim(db: Session, app_id: str, op_id: str | None):
    if not op_id:
        return None, None
    key = f"{app_id}:{op_id}"
    prior = db.get(Operation, key)
    return key, (prior.response if prior else None)


def apply_fields(db: Session, app_id: str, tenant: str, fields: dict[str, Any], *, confirmed: bool, source: str,
                 op_id: str | None = None, expected_revision: int | None = None, gated: bool = True) -> dict:
    """Validate every field first; write none if any fails (grouped updates are atomic)."""
    key, prior = _claim(db, app_id, op_id)
    if prior is not None:
        return {**prior, "duplicate": True}
    app = load(db, app_id, tenant, lock=True)
    if app.state == "submitted":
        raise Conflict("Application is already submitted. Changes need the amendment workflow.")
    if gated and not (app.consent_given and app.otp_verified):
        action, guidance = next_step(app)
        return _result(app, False, [], [{"field": "*", "code": "not_ready", "message": "Consent and code verification come first."}])

    errors, plan = [], []
    # sibling values for max_ref checks: current top-level values overlaid with this batch
    flat = {k: v.get("value") for k, v in app.data.items()}
    for path, raw in fields.items():
        try:
            spec, child, item, cid = fs.resolve_path(path)
            if path != "variant" and not fs.field_visible(spec, app.data, app.variant if "variant" not in fields else str(fields["variant"]).upper()) \
                    and spec.get("group") in ("iti", "vocational"):
                raise fs.ValidationError(path, "not_applicable", "This detail does not apply to the chosen application type. Ask which type first.")
            if child:
                ctx = dict(app.data.get(spec["id"], {}).get("value", {}).get(item, {})) if item else dict(
                    app.data.get(spec["id"], {}).get("value", {}))
                value = fs.validate_scalar(path, child, raw, ctx)
            else:
                value = fs.validate_scalar(path, spec, raw, flat)
                flat[path] = value
            if expected_revision is not None:
                ent = app.data.get(spec["id"])
                if ent and ent.get("rev", 0) > expected_revision:
                    raise Conflict("A newer value was saved while editing.", {"field": path, "current_revision": app.revision})
            plan.append((path, spec, child, item, cid, value))
        except fs.ValidationError as e:
            errors.append(e.as_dict())
    if errors:
        return _result(app, False, [], errors)

    data = json.loads(json.dumps(app.data))
    changed = []
    status_new = "confirmed" if confirmed else "captured"
    rev = app.revision + 1
    for path, spec, child, item, cid, value in plan:
        sid = spec["id"]
        ent = data.setdefault(sid, {"value": None, "status": "captured", "source": source, "rev": 0})
        if child is None:
            same = ent.get("value") == value
            if same and (ent.get("status") == "confirmed" or not confirmed):
                continue  # unchanged normalized value: no new revision, no side effects
            ent.update(value=value)
        else:
            container = ent["value"] if isinstance(ent.get("value"), dict) else {}
            ent["value"] = container
            if item:
                slot = container.setdefault(item, {"semester": int(item[3:])})
                if slot.get(cid) == value and (ent.get("status") == "confirmed" or not confirmed):
                    continue
                slot[cid] = value
            else:
                if container.get(cid) == value and (ent.get("status") == "confirmed" or not confirmed):
                    continue
                container[cid] = value
        ent.update(status=status_new, source=source, rev=rev)
        changed.append((path, spec, status_new))
    if not changed:
        return _result(app, True, [], [], {"unchanged": True})

    app.data = data
    app.revision = rev
    for path, spec, st in changed:
        _event(db, app, "field_saved", {"path": path, "status": st, "source": source})
    moved = _recompute_state(app)
    if moved:
        _event(db, app, "state_changed", {"state": moved})
    out = _result(app, True, [p for p, _, _ in changed], [])
    if key:
        db.add(Operation(op_key=key, application_id=app.id, response=out))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _, prior = _claim(db, app_id, op_id)
        if prior is not None:
            return {**prior, "duplicate": True}
        raise
    return out


def record_consent(db: Session, app_id: str, tenant: str, granted: bool) -> dict:
    app = load(db, app_id, tenant, lock=True)
    if app.state == "submitted":
        raise Conflict("Already submitted.")
    if app.consent_given != granted:
        app.consent_given = granted
        app.revision += 1
        _event(db, app, "consent", {"granted": granted})
        moved = _recompute_state(app)
        if moved:
            _event(db, app, "state_changed", {"state": moved})
    db.commit()
    return _result(app, True, [], [], {"consent_recorded": granted})


def verify_otp(db: Session, app_id: str, tenant: str, code: str) -> dict:
    app = load(db, app_id, tenant, lock=True)
    if app.state == "submitted":
        raise Conflict("Already submitted.")
    if config.OTP_MODE != "dummy":
        raise Conflict("OTP provider is not configured.")
    if not app.consent_given:
        return _result(app, False, [], [{"field": "otp", "code": "consent_first", "message": "Ask permission first."}])
    if app.otp_verified:
        return _result(app, True, [], [], {"otp_verified": True})
    if app.otp_attempts >= MAX_OTP_ATTEMPTS:
        return _result(app, False, [], [{"field": "otp", "code": "locked", "message": "Too many wrong codes. Offer a human callback."}],
                       {"otp_verified": False, "next_action": "request_help"})
    digits = "".join(c for c in code if c.isdigit())
    if digits == config.DUMMY_OTP:  # DEV ONLY: replace with a real provider before any real use
        app.otp_verified = True
        app.revision += 1
        _event(db, app, "otp_verified", {"mode": "dummy"})
        moved = _recompute_state(app)
        if moved:
            _event(db, app, "state_changed", {"state": moved})
        db.commit()
        return _result(app, True, [], [], {"otp_verified": True})
    app.otp_attempts += 1
    db.commit()
    return _result(app, False, [], [{"field": "otp", "code": "wrong_code", "message": "That code did not match. Ask once more."}],
                   {"otp_verified": False})


def request_help(db: Session, app_id: str, tenant: str, reason: str) -> dict:
    app = load(db, app_id, tenant, lock=True)
    app.help_requested = True
    app.revision += 1
    _event(db, app, "help_requested", {"reason": reason[:200]})
    db.commit()
    return _result(app, True, [], [], {"agent_message": "A human callback has been requested. Tell the candidate someone will call back, then end the call politely."})


def validate_draft(db: Session, app_id: str, tenant: str) -> dict:
    app = load(db, app_id, tenant)
    blockers = ready_blockers(app)
    return _result(app, True, [], [], {"ready": not blockers, "blockers": blockers[:8]})


def submit(db: Session, app_id: str, tenant: str, op_id: str | None = None) -> dict:
    app = load(db, app_id, tenant, lock=True)
    if app.state == "submitted":
        return _result(app, True, [], [], {"submitted": True, "already_submitted": True,
                                           "delivery_status": app.delivery_status,
                                           "agent_message": "The application was already submitted."})
    blockers = ready_blockers(app)
    if blockers:
        return _result(app, False, [], [{"field": "*", "code": "not_ready", "message": "Not complete yet: " + ", ".join(blockers[:5])}],
                       {"submitted": False, "blockers": blockers[:8]})
    app.state = "submitted"
    app.submitted_at = now()
    app.revision += 1
    app.submitted_revision = app.revision
    app.delivery_status = "recorded_locally"  # not claimed as accepted by any external system
    _event(db, app, "submitted", {"revision": app.revision})
    db.commit()
    return _result(app, True, [], [], {"submitted": True, "delivery_status": app.delivery_status,
                                       "agent_message": "Submitted and recorded. Thank the candidate and end the call. Do not claim any external system has accepted it."})


def events_after(db: Session, app_id: str, after: int, limit: int = 100) -> list[AppEvent]:
    return list(db.execute(select(AppEvent).where(AppEvent.application_id == app_id, AppEvent.id > after)
                           .order_by(AppEvent.id).limit(limit)).scalars())
