# Sarvam MCP setup (verified 2026-10-25)

## Connection
- MCP server: `sarvam-voice-agents` (authenticated via `claude mcp` / `/mcp`; re-run it there if tools stop responding).
- Agents in workspace: none yet (draft not created).
- Telephony: one Vobiz connection (`connection_successful`) with one onboarded number, `+917965481417`.
  Caller ID is a business decision: confirm before any call is placed.

## Languages (13, Sanskrit excluded by the workspace)
Assamese, Bengali, English, Gujarati, Hindi, Kannada, Konkani, Malayalam, Marathi, Odia, Punjabi, Tamil, Telugu.

## Voices
200 voices are available (all provider `sarvam`, TTS v4 beta). Only 3 cover all 13 languages including Assamese:
| Voice | internal_id |
|---|---|
| Shubh (male, companion) | 01a0e8fc-9123-73bb-bd4e-04df4741957a |
| Kangkana (female, conversational) | 01a0cf16-b474-782d-9743-13bdfc4c9a25 |
| Mouchumi (female, conversational) | 01a0cf17-1650-73b7-ac23-aad040439447 |

## Platform constraints that shape the design
- One state per agent; whole prompt in a single state. Model variant cannot be changed.
- Max call length: 60 to 1500 seconds.
- API tool headers can be bound to an **agent variable**, so a per-call `Authorization: Bearer <capability>` can be passed through a call-start variable (e.g. `auth_header` = `Bearer <jwt>`), set from the campaign cohort mapping at dispatch time.
- API tools: timeout max 30 s; the spoken reply comes from `resp_template` (Jinja over the HTTP JSON body), so the backend response must expose `missing_fields`, `validation_errors`, `next_action`.
- Campaign webhook payload: see `sarvam://schemas/webhook-payload`; no signature scheme is documented, so authenticate with a secret path/header token and verify via the Sarvam API.
- Prompt rules: English only, `##` headings only, no first/second person, no quotes, no em dashes, no language-switch instructions.
- OTP: Sarvam offers a Data Verifier tool (match against a held value). Final OTP design is pending: the backend must generate and deliver the OTP (SMS provider is not yet chosen).

## Open items
1. SMS/OTP delivery provider for identity confirmation.
2. Approved consent wording.
3. Confirm HAL form fields after Document Intelligence OCR review.

## Decisions (2026-10-25)
- Caller ID: `+917965481417` (approved by user).
- OTP identity step: dummy for now (any code accepted in dev; clearly marked, must be replaced before real use).
- Consent: agent asks only whether it may fill the form and take the information.
- Languages: all 13 listed above.
