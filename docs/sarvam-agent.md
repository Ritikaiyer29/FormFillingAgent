# Sarvam agent: HAL Kanpur Apprenticeship Form Assistant

| Item | Value |
|---|---|
| Agent id | `HAL-Kanpur--90460690-687d` |
| Committed version | 1 (draft since is version 2, uncommitted) |
| Voice | Kangkana, `01a0cf16-b474-782d-9743-13bdfc4c9a25` |
| Start language | Hindi; all 13 languages enabled with language identification (`once`) |
| Max call | 1200 s |
| Caller ID (approved) | `+917965481417`, Vobiz connection `25cb8fb2-91-7491fa4c-891a` |
| Backend | `https://formfilling-api.onrender.com` |
| Goal | criterion "Application submitted": `call_outcome == submitted` |

Runtime prompt: [sarvam/runtime_prompt.md](../sarvam/runtime_prompt.md) (the committed text).
Intro (English source, platform generated the other 12): "Hello, this is an automated assistant helping with the HAL Kanpur apprenticeship application form. Is this a good time to talk?"
Voicemail: "This is an automated call about the HAL Kanpur apprenticeship application form. Please call the institute helpline on 0512-2458752, between 9 AM and 3 PM, Monday to Friday."
Silence nudges: 3 template nudges at 8, 10 and 12 seconds, then the call ends. The last one makes no callback promise.

## Variables
- `auth_header` (call-start input): `Bearer <per-call capability>`, minted by `POST /api/sessions/{id}/capability` at dispatch. Mapped by the cohort upload (variables go in the mapping's variables block, not at top level). Never in the prompt.
- `call_outcome` (post-call extraction): submitted, partial, consent_declined, wrong_person, callback_requested, verification_failed, technical_failure.

## Tools (all POST, `Authorization` from `auth_header`, 30 s timeout)
| Tool | Endpoint | Spoken reply template |
|---|---|---|
| get_session_context | /tools/context | agent_message, variant, missing_fields |
| record_consent | /tools/consent | agent_message |
| verify_code | /tools/otp | agent_message |
| save_field | /tools/save | agent_message, missing_fields, next_action |
| check_application | /tools/validate | ready, blockers, agent_message |
| submit_application | /tools/submit | submitted, agent_message |
| request_human_callback | /tools/help | agent_message |

`agent_message` is composed by the backend and already carries validation errors and the next step.
The response mapping has NOT yet been seen end to end by a live agent; it is verified only by the backend tests.

## Known gaps and decisions needed
1. **Notice deadline.** The advertisement's last date for receipt is 30/01/2026, which has passed. Confirm the form is still open before any real call.
2. **OTP is a dummy** (code `123456`, nothing is sent). The prompt asks for "the verification code for this number", which a real candidate cannot have. Test calls only until a real SMS provider is added.
3. **Render free tier cold start** can take about 50 s, longer than the 30 s tool timeout. Always call the capability endpoint (which wakes the API) right before dialing, or move to a paid instance.
4. **No printable form yet.** The agent says details are recorded and that photo, signature and documents are not taken by phone, but promises no printout or link, because no PDF export exists yet.
5. **Brand wording.** Intro and voicemail say "HAL Kanpur apprenticeship application form" without claiming HAL itself is calling. Confirm the organisation name you want spoken.
6. **No dispatcher yet.** Nothing places calls. A test call needs your explicit go-ahead and a verified number.
7. Platform quirks: `numbers_in_indic` was stored as true by the platform; `get` with `tool_specs` is not enabled for this org.

## Outbound dispatch (UI "Place call")
- Standing campaign `formfill-si-f81efbff-d96a` (scheduled, 0 users, ends 2027-01-20 because Sarvam caps campaigns at 90 days; create a new one then and update `SARVAM_CAMPAIGN_ID`).
- `POST /api/sessions/{id}/call` mints the per-call token and streams a one-user cohort (`app_variables.auth_header`, `app_overrides.initial_language_name`) to the campaign via `X-API-Key`. Needs `SARVAM_API_KEY`, `SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID`, `SARVAM_CAMPAIGN_ID` on the API service.
- Campaign dialling does not need the phone-number verification that `place_test_call` needs.
- `place_test_call` cannot inject `auth_header` (it silently drops it), so it is not used for end-to-end tests.
