# HealFlow AI Receptionist

A full-time digital front-desk employee: answers patients, books and manages
appointments, runs follow-ups, detects emergencies, and hands off to humans
when it should — with a live staff workspace to supervise and take over.

This documents what is **live in the running stack** vs **adapter-ready**
(built, waiting on an external credential), and how the pieces fit.

---

## Where it runs

Same AI, one pipeline, every channel is an event source into it:

| Channel | Status | Notes |
|---|---|---|
| Website chat | **live** | `/chat`, WebSocket delivery, primary demo surface |
| WhatsApp | **adapter-ready** | `/webhooks/whatsapp` (Meta Cloud API) — set `WHATSAPP_VERIFY_TOKEN` + `WHATSAPP_ACCESS_TOKEN`, point the webhook at the clinic number |
| SMS / Voice / Email | **adapter-ready** | notification router has channel slots; each needs a provider (Twilio/STT/SMTP) wired to the same message pipeline |

Every inbound turn — text, and (adapter-ready) voice notes and images — becomes
a `Message` on the patient's conversation and flows through the one agent path.

---

## What the AI does (all live)

Driven by a Claude tool-use agent (`src/ai.py` + `src/agent_tools.py`) with a
deterministic fallback router when no `ANTHROPIC_API_KEY` is set, so booking,
info, meds, queue, and FAQ **all work without an API key**.

- **Booking engine** — checks doctor availability, prevents double booking
  (DB partial-unique index, not just app logic), books, cancels, reschedules,
  lists the patient's appointments, quotes the fee.
- **Clinic info** — hours, location, parking, consultation fee.
- **Medications** — lists active prescriptions; logs "done" against reminders.
- **Recovery** — logs pain 0–10 against the active follow-up plan.
- **Queue** — "how long is the wait?" → patients-ahead + estimate.
- **FAQ** — answers only from clinic-approved knowledge (`clinic_knowledge`),
  never free-improvised medical advice.
- **Memory** — per-patient profile (language, insurance, conditions,
  high-priority flag) + conversation history are assembled and handed to the
  model; it never asks for what the record already holds.
- **Language** — auto-detects en/hi/kn/ta/te/ml by script and replies in kind;
  the preference is remembered.

### Emergency detection (live, non-bypassable)
A deterministic keyword+pattern layer runs **before any model call**
(`detect_emergency`). Chest pain / breathing / stroke / heavy bleeding /
suicidal ideation / anaphylaxis / high fever → the runtime halts normal flow,
returns the approved emergency script (clinic emergency line + 112), raises an
`Escalation` row, and flags the patient high-priority. It cannot be talked out
of escalating; a model can only *add* an escalation, never suppress one.

### Handoff (live)
Emergencies and unacknowledged escalations surface in the staff workspace and
morning dashboards. Staff take over any conversation at any time; while a human
holds it, the runtime stays silent (below).

---

## The reception workspace (`/reception`)

Staff-only 3-pane console. Requires a staff/doctor/clinic_admin/admin login
(mint one with `healflow-devops/scripts/create-staff-user.sh`).

- **Left — conversations**: every patient thread, escalations first then
  recency, with unread counts, 🚨 escalation badge, and an **AI / Human** chip
  showing who currently owns the thread.
- **Middle — thread**: patient / assistant / staff messages, live over
  WebSocket. Composer with **✨ Suggest reply** (drafts what the AI *would*
  say, editable, never auto-sent) and **Take over / Resume AI**.
- **Right — context**: upcoming appointments, medication adherence bar, recent
  pain check-ins, open escalations with **Acknowledge**, quick actions.

### Takeover / resume mechanics
- **Take over** (or simply sending a manual reply) sets `ai_paused = true` on
  the patient profile. While paused, the patient's messages get **no automatic
  assistant reply** — the human is driving.
- **Resume AI** clears the flag; the runtime answers again on the next message.
- This is the supervision boundary: AI executes by default, a human can seize
  or return control per-conversation instantly.

---

## Privacy & authorization (enforced, tested)

- **Patients see only their own conversation.** `GET /api/messages` scopes to
  the caller's `conversation_user_id`; a patient cannot read another patient's
  thread (regression-tested in `tests/test_reception.py`).
- **Staff endpoints require a staff role** (`/api/reception/*`, `/api/staff/*`,
  `/api/analytics/*`) — 403 otherwise.
- **WebSocket is identity-aware**: patient sockets receive only their own
  conversation's messages; staff sockets receive all (for the live workspace).
- Role escalation is **not** exposed over the API — staff accounts are minted
  via the DB by an operator (`create-staff-user.sh`).

---

## Structured tools (audited)

The agent acts only through typed tools, never free-text side effects:
`get_availability`, `book_appointment`, `cancel_appointment`,
`reschedule_appointment`, `get_my_appointments`, `get_clinic_info`,
`list_doctors`, `get_my_medications`, `log_medication_taken`, `log_pain_level`,
`get_queue_status`, `search_clinic_knowledge`. Each validates inputs and its
effects are events on the record. The Meridian kernel (`src/meridian/`) records
the trust ledger and enforces autonomy tiers with permanent ceilings
(prescriptions/diagnosis/consent can never auto-execute).

---

## Automation (live, Celery beat)

Appointment reminders (24h/2h), medication reminders with 30-min nag +
clinic-notify on repeated ignore, daily recovery check-ins with pain capture,
post-visit feedback requests, no-show marking. Follow-ups adapt to patient
responses rather than firing on a fixed script.

---

## Configuration

`healflow-devops/.env` (see `.env.example`):

```
AI_REPLY_ENABLED=true               # master switch for auto-replies
ANTHROPIC_API_KEY=                  # empty → deterministic fallback router
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
WHATSAPP_VERIFY_TOKEN=              # set to activate WhatsApp webhook
WHATSAPP_ACCESS_TOKEN=              # Meta Cloud API send token
```

Bring the stack up: `docker compose -f healflow-devops/docker-compose.yml up -d`
(migrations 0001–0005 run automatically via the one-shot `migrate` service).

## Demo flow

1. Patient at `https://localhost/chat` (register or `demo3@example.com` /
   `demopass123`): "Can I see Dr. Sharma tomorrow?" → slots → book.
2. Staff at `https://localhost/reception` (`reception@smilecare.example` /
   `staffpass123`): the conversation appears live. Click it, hit **Take over**,
   type a reply — the patient receives it and the AI stays quiet. **Resume AI**
   to hand control back.
3. Emergency test: patient sends "heavy bleeding" → emergency script fires,
   escalation appears in the workspace context pane and the reception dashboard.

## Known adapter gaps (built, need a credential/provider)
- WhatsApp send/receive — needs Meta Business number + tokens.
- Voice notes — transcriber interface stubbed; needs an STT provider (Indic).
- SMS/voice/email channels — router slots exist; need Twilio/SMTP wiring.
- Payments — invoice schema only; needs a gateway (Razorpay/Stripe) per market.
