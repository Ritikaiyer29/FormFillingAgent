import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["ADMIN_API_KEY"] = "admin-test-key"
os.environ["SESSION_CAPABILITY_SIGNING_SECRET"] = "x" * 32
os.environ["OTP_MODE"] = "dummy"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import formschema as fs

ADMIN = {"Authorization": "Bearer admin-test-key"}
VALID_AADHAAR = "234567890124"  # checked below


def _aadhaar():
    base = "23456789012"
    for d in range(10):
        if fs.verhoeff_ok(base + str(d)):
            return base + str(d)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def new_session(client, variant="ITI"):
    s = client.post("/api/sessions", json={"phone": "9876543210", "language": "Hindi", "variant": variant}, headers=ADMIN).json()
    cap = client.post(f"/api/sessions/{s['id']}/capability", headers=ADMIN).json()
    return s["id"], {"Authorization": cap["authorization_header"]}


def onboard(client, h):
    assert client.post("/tools/consent", json={"granted": True}, headers=h).json()["saved"]
    assert client.post("/tools/otp", json={"code": "123456"}, headers=h).json()["otp_verified"]


ITI_FIELDS = {
    "variant": "ITI",
    "apprenticeship_reg_no": "UP/2024/123456", "candidate_name": "ravi kumar", "father_name": "mohan kumar",
    "mother_name": "sita devi", "dob": "15/06/2003", "gender": "male", "aadhaar_no": _aadhaar(), "pan_no": "abcde1234f",
    "hs_marks_obtained": 420, "hs_total_marks": 600, "iti_institute": "Govt ITI Kanpur Nagar", "iti_trade": "Fitter",
    "iti_pass_year": 2024, "iti_semester_marks.1.total": 500, "iti_semester_marks.1.obtained": 400,
    "certificate_type": "NCVT", "category": "OBC", "category_cert_enclosed": "yes", "domicile_cert_enclosed": "yes",
    "address.line1": "12 Nehru Nagar", "address.district": "Kanpur Nagar", "address.state": "Uttar Pradesh",
    "address.pin": "208008", "mobile": "+91 98765 43210", "email": "Ravi@Example.com", "parent_mobile": "9123456780",
}


def test_gates_before_consent(client):
    sid, h = new_session(client)
    r = client.post("/tools/save", json={"field_id": "candidate_name", "value": "RAVI"}, headers=h).json()
    assert r["saved"] is False and r["next_action"] == "ask_consent"


def test_happy_path_and_submission(client):
    sid, h = new_session(client)
    onboard(client, h)
    r = client.post("/tools/save", json={"fields": ITI_FIELDS, "confirmed": True}, headers=h).json()
    assert r["saved"] and not r["validation_errors"], r
    snap = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()
    assert snap["data"]["candidate_name"]["value"] == "RAVI KUMAR"
    assert snap["data"]["mobile"]["value"] == "9876543210"
    assert snap["derived"]["hs_percentage"] == 70.0 and snap["derived"]["iti_percentage"] == 80.0
    assert snap["missing"] == ["declaration_accepted"] or snap["state"] == "collecting"
    # submit blocked until declaration accepted
    assert client.post("/tools/submit", headers=h).json()["submitted"] is False
    client.post("/tools/save", json={"field_id": "declaration_accepted", "value": "yes", "confirmed": True}, headers=h)
    s1 = client.post("/tools/submit", headers=h).json()
    assert s1["submitted"] and s1["delivery_status"] == "recorded_locally"
    s2 = client.post("/tools/submit", headers=h).json()
    assert s2["already_submitted"]
    # post-submission edits refused
    assert client.post(f"/api/sessions/{sid}/fields", json={"fields": {"candidate_name": "X Y"}}, headers=ADMIN).status_code == 409
    assert client.post("/tools/save", json={"field_id": "candidate_name", "value": "ZZ"}, headers=h).status_code == 409


def test_grouped_update_is_atomic_and_errors_visible(client):
    sid, h = new_session(client)
    onboard(client, h)
    r = client.post("/tools/save", json={"fields": {"candidate_name": "ASHA", "aadhaar_no": "123456789012"}}, headers=h).json()
    assert r["saved"] is False
    assert r["validation_errors"][0]["field"] == "aadhaar_no"
    assert "aadhaar_no" in r["agent_message"]
    snap = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()
    assert "candidate_name" not in snap["data"]  # nothing written


def test_marks_bound_and_wrong_variant_field(client):
    sid, h = new_session(client, variant="VOCATIONAL")
    onboard(client, h)
    r = client.post("/tools/save", json={"fields": {"hs_total_marks": 500, "hs_marks_obtained": 600}}, headers=h).json()
    assert r["validation_errors"][0]["code"] == "exceeds_total"
    r = client.post("/tools/save", json={"field_id": "iti_trade", "value": "Fitter"}, headers=h).json()
    assert r["validation_errors"][0]["code"] == "not_applicable"


def test_idempotency_and_unchanged(client):
    sid, h = new_session(client)
    onboard(client, h)
    body = {"field_id": "candidate_name", "value": "Asha Rani", "op_id": "op-1"}
    a = client.post("/tools/save", json=body, headers=h).json()
    b = client.post("/tools/save", json=body, headers=h).json()
    assert b["duplicate"] and b["application_revision"] == a["application_revision"]
    c = client.post("/tools/save", json={"field_id": "candidate_name", "value": "ASHA RANI"}, headers=h).json()
    assert c.get("unchanged") and c["application_revision"] == a["application_revision"]


def test_stale_operator_edit_conflicts(client):
    sid, h = new_session(client)
    onboard(client, h)
    client.post("/tools/save", json={"field_id": "candidate_name", "value": "ASHA"}, headers=h)
    rev_seen = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()["revision"]
    client.post("/tools/save", json={"field_id": "candidate_name", "value": "ASHA RANI"}, headers=h)
    r = client.post(f"/api/sessions/{sid}/fields", json={"fields": {"candidate_name": "ASHA K"}, "expected_revision": rev_seen}, headers=ADMIN)
    assert r.status_code == 409


def test_auth_revocation_and_tenant(client):
    sid, h = new_session(client)
    assert client.post("/tools/context", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.post("/tools/context", headers=h).status_code == 200
    client.post(f"/api/sessions/{sid}/revoke", headers=ADMIN)
    assert client.post("/tools/context", headers=h).status_code == 401
    assert client.get(f"/api/sessions/{sid}", headers={"Authorization": "Bearer nope"}).status_code == 401
    # a stream token for one session cannot open another
    sid2, _ = new_session(client)
    tok = client.post(f"/api/sessions/{sid}/stream-token", headers=ADMIN).json()["token"]
    assert client.get(f"/api/sessions/{sid2}/events?token={tok}").status_code == 403


def test_wrong_otp_and_dummy_flag(client):
    sid, h = new_session(client)
    client.post("/tools/consent", json={"granted": True}, headers=h)
    r = client.post("/tools/otp", json={"code": "000000"}, headers=h).json()
    assert r["otp_verified"] is False


def test_call_end_webhook(client):
    sid, h = new_session(client)
    body = {"campaign_id": "camp-1", "user_identifier": sid, "completion_status": "completed",
            "connectivity_status": "connected", "duration": 62.0, "final_agent_variables": {"call_outcome": "partial"}}
    assert client.post("/webhooks/call?t=wrong", json=body).status_code == 401
    assert client.post("/webhooks/call?t=hook-secret", json={**body, "campaign_id": "other"}).json() == {"ignored": True}
    assert client.post("/webhooks/call?t=hook-secret", json=body).json() == {"updated": True}
    snap = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()
    assert snap["call_status"] == "completed"
    assert client.post("/tools/context", headers=h).status_code == 401  # token revoked when the call ended
    body["connectivity_status"] = "no_answer"
    client.post("/webhooks/call?t=hook-secret", json=body)
    assert client.get(f"/api/sessions/{sid}", headers=ADMIN).json()["call_status"] == "no_answer"


def test_agent_chosen_variant_unlocks_its_fields_and_same_number(client):
    sid, h = new_session(client, variant=None)
    onboard(client, h)
    save = lambda f, v, c=False: client.post("/tools/save", json={"field_id": f, "value": v, "confirmed": c}, headers=h).json()
    assert not save("iti_institute", "Govt ITI Kanpur Nagar")["saved"]          # type not chosen yet
    assert save("variant", "ITI")["saved"]
    assert client.get(f"/api/sessions/{sid}", headers=ADMIN).json()["variant"] == "ITI"
    assert save("iti_institute", "Govt ITI Kanpur Nagar")["saved"]              # no confirmation of the type needed
    r = save("iti_pass_year", "2022")
    assert not r["saved"] and "2023" in r["agent_message"]
    assert save("mobile", "SAME_AS_CALLED")["saved"]
    snap = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()
    assert snap["data"]["mobile"]["value"] == "9876543210"
    assert "variant" not in snap["missing"]


def test_filled_form_ops_and_pdf(client):
    sid, h = new_session(client)
    onboard(client, h)
    client.post("/tools/save", json={"field_id": "candidate_name", "value": "ravi kumar"}, headers=h)
    client.post("/tools/save", json={"field_id": "category", "value": "OBC"}, headers=h)
    snap = client.get(f"/api/sessions/{sid}", headers=ADMIN).json()
    assert snap["form"]["pages"] == ["a1", "a2"]
    texts = {o["path"]: o for o in snap["form"]["ops"]}
    assert texts["candidate_name"]["lines"] == ["RAVI KUMAR"] and texts["candidate_name"]["page"] == 0
    assert texts["category"]["kind"] == "tick" and texts["category"]["page"] == 1
    r = client.get(f"/api/sessions/{sid}/form.pdf", headers=ADMIN)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "attachment" in r.headers["content-disposition"]
    unknown, _ = new_session(client, variant=None)
    assert client.get(f"/api/sessions/{unknown}", headers=ADMIN).json()["form"]["ops"] == []
    assert client.get(f"/api/sessions/{unknown}/form.pdf", headers=ADMIN).status_code == 409
