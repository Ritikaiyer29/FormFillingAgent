import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import auth, config
from . import formschema as fs
from . import service as svc
from .db import SessionLocal, init_db

LANGUAGES = ["Assamese", "Bengali", "English", "Gujarati", "Hindi", "Kannada", "Konkani",
             "Malayalam", "Marathi", "Odia", "Punjabi", "Tamil", "Telugu"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="FormFillingAgent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def db_session():
    with SessionLocal() as db:
        yield db


@app.exception_handler(svc.NotFound)
async def _nf(_, __):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.exception_handler(svc.Conflict)
async def _conflict(_, exc: svc.Conflict):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.message, **exc.extra}, status_code=409)


@app.get("/healthz")
def healthz():
    return {"ok": True, "schema_version": fs.SCHEMA_VERSION}


# ---------------------------------------------------------------- admin API
@app.get("/api/schema")
def get_schema(_: str = Depends(auth.require_admin)):
    return {**fs.SCHEMA, "languages": LANGUAGES}


class NewSession(BaseModel):
    phone: str = Field(pattern=r"^\+?[0-9]{10,13}$")
    language: str = "Hindi"
    variant: str | None = None


@app.post("/api/sessions", status_code=201)
def create_session(body: NewSession, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    if body.language not in LANGUAGES:
        raise HTTPException(422, "Unsupported language")
    if body.variant not in (None, "ITI", "VOCATIONAL"):
        raise HTTPException(422, "variant must be ITI or VOCATIONAL")
    digits = "".join(c for c in body.phone if c.isdigit())
    phone = "+91" + digits[-10:] if len(digits) >= 10 else body.phone
    return svc.snapshot(svc.create_application(db, tenant, phone, body.language, body.variant, "operator"))


@app.get("/api/sessions")
def list_sessions(tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    from sqlalchemy import select
    from .db import Application
    rows = db.execute(select(Application).where(Application.tenant_id == tenant)
                      .order_by(Application.created_at.desc()).limit(100)).scalars()
    return [{"id": a.id, "phone": a.phone, "state": a.state, "call_status": a.call_status, "variant": a.variant,
             "revision": a.revision, "created_at": a.created_at.isoformat()} for a in rows]


@app.get("/api/sessions/{sid}")
def get_session(sid: str, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    return svc.snapshot(svc.load(db, sid, tenant))


@app.post("/api/sessions/{sid}/capability")
def issue_capability(sid: str, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    """Mint the per-call tool token. Call this at dispatch time, not earlier. Locks the call language."""
    app_ = svc.load(db, sid, tenant, lock=True)
    if app_.state == "submitted":
        raise svc.Conflict("Already submitted.")
    app_.capability_nonce = str(uuid.uuid4())  # replaces any earlier token
    app_.language_locked = True
    db.commit()
    token = auth.mint(app_.id, tenant, app_.capability_nonce, auth.AUD_TOOLS, auth.TOOL_ACTIONS, config.CAPABILITY_TTL)
    return {"token": token, "authorization_header": f"Bearer {token}", "expires_in": config.CAPABILITY_TTL}


@app.post("/api/sessions/{sid}/call")
def place_call(sid: str, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    """Dial the candidate: mint the per-call token and stream a one-user cohort into the standing campaign."""
    import time

    import httpx
    if not (config.SARVAM_API_KEY and config.SARVAM_ORG_ID and config.SARVAM_WORKSPACE_ID and config.SARVAM_CAMPAIGN_ID):
        raise HTTPException(503, "Calling is not configured: set SARVAM_API_KEY, SARVAM_ORG_ID, SARVAM_WORKSPACE_ID and SARVAM_CAMPAIGN_ID.")
    app_ = svc.load(db, sid, tenant, lock=True)
    if app_.state == "submitted":
        raise svc.Conflict("Already submitted.")
    app_.capability_nonce = str(uuid.uuid4())
    app_.language_locked = True
    token = auth.mint(app_.id, tenant, app_.capability_nonce, auth.AUD_TOOLS, auth.TOOL_ACTIONS, config.CAPABILITY_TTL)
    phone, language = app_.phone, app_.call_language
    app_.call_status = "dialing"
    db.commit()
    url = (f"{config.SARVAM_BASE}/orgs/{config.SARVAM_ORG_ID}/workspaces/{config.SARVAM_WORKSPACE_ID}"
           f"/campaigns/{config.SARVAM_CAMPAIGN_ID}/cohorts/stream")
    body = {"name": f"call-{sid[:8]}-{int(time.time())}",
            "users": [{"user_phone_number": phone, "user_identifier": sid,
                       "app_variables": {"auth_header": f"Bearer {token}"},
                       "app_overrides": {"initial_language_name": language}}]}
    try:
        r = httpx.post(url, json=body, headers={"X-API-Key": config.SARVAM_API_KEY}, timeout=25)
    except httpx.HTTPError:
        r = None
    if r is None or r.status_code >= 300:
        app_ = svc.load(db, sid, tenant, lock=True)
        app_.call_status, app_.capability_nonce = "not_started", None
        db.commit()
        raise HTTPException(502, f"Sarvam refused the call request ({r.status_code if r is not None else 'no response'}).")
    return {"dialing": True, "cohort_id": r.json().get("cohort_id")}


@app.post("/api/sessions/{sid}/revoke")
def revoke(sid: str, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    app_ = svc.load(db, sid, tenant, lock=True)
    app_.capability_nonce = None
    db.commit()
    return {"revoked": True}


class OperatorEdit(BaseModel):
    fields: dict[str, Any]
    expected_revision: int | None = None


@app.post("/api/sessions/{sid}/fields")
def operator_edit(sid: str, body: OperatorEdit, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    """Operator correction. If expected_revision is sent and any touched field changed since, answers 409."""
    return svc.apply_fields(db, sid, tenant, body.fields, confirmed=True, source="operator",
                            expected_revision=body.expected_revision, gated=False)


@app.post("/api/sessions/{sid}/stream-token")
def stream_token(sid: str, tenant: str = Depends(auth.require_admin), db=Depends(db_session)):
    app_ = svc.load(db, sid, tenant)
    return {"token": auth.mint(app_.id, tenant, "stream", auth.AUD_STREAM, ["stream"], 300)}


@app.get("/api/sessions/{sid}/events")
async def stream(sid: str, request: Request, token: str = Query(...), after: int = Query(0)):
    """SSE: initial snapshot, then durable events by id. Replays from Last-Event-ID or ?after=."""
    claims = auth.decode(token, auth.AUD_STREAM)
    if claims["sub"] != sid:
        raise HTTPException(403, "Token is for another session")
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else after

    def snap():
        with SessionLocal() as db:
            return svc.snapshot(svc.load(db, sid, claims["tenant"]))

    def fetch(c):
        with SessionLocal() as db:
            return [(e.id, e.revision, e.type, e.payload) for e in svc.events_after(db, sid, c)]

    async def gen():
        nonlocal cursor
        s = await run_in_threadpool(snap)
        yield f"event: snapshot\ndata: {json.dumps(s)}\n\n"
        idle = 0
        while not await request.is_disconnected():
            rows = await run_in_threadpool(fetch, cursor)
            for eid, rev, typ, payload in rows:
                cursor = eid
                yield f"id: {eid}\nevent: change\ndata: {json.dumps({'id': eid, 'revision': rev, 'type': typ, **payload})}\n\n"
            idle = 0 if rows else idle + 1
            if idle and idle % 15 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- Sarvam tool API
def _tenant_app(db, claims):
    app_ = svc.load(db, claims["sub"], claims["tenant"])
    if app_.capability_nonce != claims["nonce"]:
        raise HTTPException(401, "Token revoked")
    return app_


class SaveBody(BaseModel):
    field_id: str | None = None
    value: Any = None
    fields: dict[str, Any] | str | None = None
    confirmed: bool = False
    op_id: str | None = None


@app.post("/tools/context")
def tool_context(claims=Depends(auth.tool_claims("context")), db=Depends(db_session)):
    a = _tenant_app(db, claims)
    return svc._result(a, True, [], [], {"variant": a.variant, "call_language": a.call_language,
                                          "dialed_number_hint": a.phone[-4:]})


class ConsentBody(BaseModel):
    granted: bool = True


@app.post("/tools/consent")
def tool_consent(body: ConsentBody, claims=Depends(auth.tool_claims("consent")), db=Depends(db_session)):
    _tenant_app(db, claims)
    return svc.record_consent(db, claims["sub"], claims["tenant"], body.granted)


class OtpBody(BaseModel):
    code: str


@app.post("/tools/otp")
def tool_otp(body: OtpBody, claims=Depends(auth.tool_claims("otp")), db=Depends(db_session)):
    _tenant_app(db, claims)
    return svc.verify_otp(db, claims["sub"], claims["tenant"], body.code)


@app.post("/tools/save")
def tool_save(body: SaveBody, claims=Depends(auth.tool_claims("save")), db=Depends(db_session)):
    _tenant_app(db, claims)
    fields = body.fields
    if isinstance(fields, str):
        try:
            fields = json.loads(fields)
            assert isinstance(fields, dict)
        except Exception:
            raise HTTPException(422, "fields must be a JSON object")
    if not fields:
        if not body.field_id:
            raise HTTPException(422, "field_id or fields required")
        fields = {body.field_id: body.value}
    return svc.apply_fields(db, claims["sub"], claims["tenant"], fields, confirmed=body.confirmed,
                            source="agent", op_id=body.op_id)


@app.post("/tools/validate")
def tool_validate(claims=Depends(auth.tool_claims("validate")), db=Depends(db_session)):
    _tenant_app(db, claims)
    return svc.validate_draft(db, claims["sub"], claims["tenant"])


class HelpBody(BaseModel):
    reason: str = ""


@app.post("/tools/help")
def tool_help(body: HelpBody, claims=Depends(auth.tool_claims("help")), db=Depends(db_session)):
    _tenant_app(db, claims)
    return svc.request_help(db, claims["sub"], claims["tenant"], body.reason)


@app.post("/tools/submit")
def tool_submit(claims=Depends(auth.tool_claims("submit")), db=Depends(db_session)):
    _tenant_app(db, claims)
    return svc.submit(db, claims["sub"], claims["tenant"])
