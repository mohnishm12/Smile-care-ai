# The Meridian Ubiquitous Language

Status: LAW (companion to the Constitution). One term, one meaning. If a term
is not defined here, it may not appear in code, schemas, events, prompts, or
UI. New terms enter only by amendment PR to this file, reviewed like code.

Conventions: code identifiers are given as `snake_case`. Event types are
PastTense PascalCase. "MUST/NEVER" here carry constitutional force.

Enforcement: CI greps for banned synonyms (§40) in identifiers, event types,
and UI strings. A hit is a failing build, not a warning.

---

## Identity & structure

### 1. Organization — `organization`
**Is:** the legal/commercial entity that owns one or more Clinics and holds the
billing relationship with Meridian.
**Is not:** a care setting. Nothing clinical attaches to an Organization.
**Example:** "SmileCare Health Pvt Ltd" owning four Clinics.
**Counterexample:** a hospital *department* is not an Organization; it is a
Clinic within one.
**Lifecycle:** `created → active → suspended → closed`.
**Events:** `OrganizationCreated`, `ClinicAdded`, `OrganizationSuspended`.
**Related:** Clinic (child), Trust (scoped per Clinic, never per Organization).

### 2. Clinic — `clinic`
**Is:** one care setting and one tenancy boundary: its own patients, providers,
schedule, WhatsApp number, autonomy configuration, and protocol packs.
`tenant_id` == `clinic_id`, always.
**Is not:** a location field. Two rooms in one building sharing staff and
schedule are one Clinic; two branches with separate schedules are two.
**Lifecycle:** `onboarding → live → paused → offboarded`.
**Events:** `ClinicOnboarded`, `ClinicConfigured`, `AutonomyTierChanged`.
**Related:** Organization (parent), PatientRecord (per person × this clinic).

### 3. Person — `person`
**Is:** one human being: identity, contact handles, auth credentials. Global
across Clinics.
**Is not:** a patient. Person is who you are; Patient is a role you hold at a
Clinic. Staff are also Persons.
**Events:** `PersonRegistered`, `ContactHandleVerified`.
**Related:** Patient, Provider (roles a Person holds).

### 4. Patient — `patient`
**Is:** the role a Person holds when enrolled for care at a Clinic. All
clinical meaning lives in the PatientRecord (§5) this enrollment opens.
**Is not:** a "user", "customer", "client", "contact", or "lead" — those words
are banned. Not a row that staff "create": enrollment is an event with consent.
**Example:** Rahul is one Person; he is a Patient at SmileCare Indiranagar and
a Patient at an eye clinic — two PatientRecords, one Person.
**Lifecycle:** `enrolled → active → dormant (no activity 18 mo) → archived`;
erasure per jurisdiction procedure.
**Events:** `PatientEnrolled`, `ConsentGranted/Revoked`, `PatientArchived`.
**Related:** Person, PatientRecord, Care Team.

### 5. PatientRecord — `patient_record`
**Is:** THE aggregate: the append-only stream of Events for one Patient at one
Clinic. The single source of clinical truth.
**Is not:** a table, a profile page, or a "chart" you edit. It is never
mutated; it only grows.
**Events:** it *is* events; stream id `patient-{person_id}-{clinic_id}`.
**Related:** Timeline (its rendering), Projection (its derivations).

### 6. Provider — `provider`
**Is:** a credentialed clinician role (doctor, dentist, physio) held by a
Person at a Clinic, carrying schedule template, specialty, signing authority,
and style profile.
**Is not:** "doctor" as a code identifier for all staff — reception is Staff
(`staff`), not Provider. Not a login: a Provider may exist before their Person
ever signs in.
**Lifecycle:** `credentialed → active → on_leave → departed`.
**Events:** `ProviderAdded`, `ScheduleTemplateSet`, `ProviderDeparted`.
**Related:** Care Team, Encounter (a Provider conducts them), Approval (signing).

### 7. Care Team — `care_team`
**Is:** the set of Providers and Staff currently responsible for a
PatientRecord: exactly one `primary_provider` plus zero or more members.
Determines routing of Escalations, Tasks, and Approvals for that Patient.
**Is not:** everyone at the Clinic; not an org-chart; not static — membership
changes are events.
**Events:** `CareTeamAssigned`, `PrimaryProviderChanged`.
**Related:** Escalation (routed to it), Notification (addressed via it).

---

## The record

### 8. Event — `event`
**Is:** an immutable, ordered fact: something that happened, with envelope
(`event_id`, `stream_id`, `seq`, `type`, `v`, `occurred_at`, `recorded_at`,
`actor`, `causation_id`, `correlation_id`) and typed payload. The only way
state exists.
**Is not:** a message (transport), a log line (diagnostics), a webhook
(integration), or a UI "event" (interaction). Those words may not be shortened
to "event" in code.
**Counterexample:** an HTTP request is not an Event; the state change it
caused is.
**Lifecycle:** appended → (optionally) upcasted at read → never mutated,
never deleted (crypto-shred payload only, envelope remains).
**Related:** Command (requests it), Projection (consumes it), Ledger (a family
of it).

### 9. Clinical Event
**Is:** the subset of Events whose payload carries care meaning
(`ObservationRecorded`, `PrescriptionSigned`, `EmergencyDetected`, ...). PHI
encryption and retention rules key off this classification (`clinical: true`
in the type registry).
**Is not:** a separate table or stream — a classification of Events.
**Related:** Event, Audit (clinical events have the strictest retention).

### 10. Command — `command`
**Is:** a validated request to change state: intent + parameters + principal.
Handled exactly once; emits zero or more Events. Named imperative
(`BookAppointment`).
**Is not:** an HTTP endpoint (transport), an Event (fact), or a Tool (the AI's
doorway to a Command).
**Lifecycle:** `submitted → validated → risk_classed → {executed | parked_as_draft | rejected}`.
**Related:** Event (output), Action (an AI-initiated Command with ledger
wrapping), Risk (classification input).

### 11. Projection — `projection`
**Is:** a pure, idempotent, checkpointed function folding Events into a Read
Model. Rebuildable from replay at any time.
**Is not:** a cache (may be stale but never wrong), a view (SQL construct), or
a place business rules live.
**Events:** consumes all; emits none (engines emit; projectors only fold).
**Related:** Read Model (its output), Event (its input).

### 12. Read Model — `read_model`, tables `rm_*`
**Is:** a disposable, query-optimized table owned by exactly one Projection.
The only thing APIs and analytics may query.
**Is not:** a source of truth; never written by handlers, humans, or scripts.
**Counterexample:** `rm_schedule`'s unique slot index *enforces* the
double-booking invariant operationally, but the booking Events remain the
truth — rebuilds recreate the index.
**Related:** Projection (owner), Timeline (not a read model — a windowed
stream view).

### 13. Timeline
**Is:** the chronological rendering of a PatientRecord (or filtered subset)
for humans: Events with type filters, windowing, and citation anchors.
**Is not:** a new datastore, and not "history" (banned as identifier) — there
is only the record.
**Related:** Evidence (citations point into it), Card `timeline` (its UI form).

### 14. Ledger — `ledger`
**Is:** the Event family recording everything the Runtime proposes and does:
`ActionProposed/Approved/Denied/Executed/Failed/RolledBack` plus outcome
annotations. The substrate Trust is computed from and the liability record.
**Is not:** a separate database; not financial (never call billing tables
"ledger"); not optional for any Action.
**Related:** Action, Approval, Trust, Audit.

### 15. Audit
**Is:** the *capability* to answer "who did/knew what, when, and why" — served
entirely by the Event stream + integrity chain via the timeline API.
**Is not:** a table (`audit_log` may not exist), a module, or an afterthought.
"Audit trail" as a noun for a datastore is banned.
**Related:** Event (the substance), Ledger (the AI-conduct slice).

---

## Perception & judgment

### 16. Signal — `signal`
**Is:** raw inbound reality before interpretation: a WhatsApp message, a voice
note, an uploaded photo, a wearable sample, a webhook. Persisted as ingestion
Events with provenance.
**Is not:** an Observation (interpreted) or a Finding (concluded). The
pipeline is Signal → Observation → Finding, strictly in that order.
**Events:** `MessageReceived`, `VitalsSampleIngested`, `DocumentIngested`.

### 17. Observation — `observation`
**Is:** one structured clinical data point extracted from a Signal or entered
by a Provider: `{kind, value, unit?, occurred_at, source, confidence}`.
Pain 6/10, temp 38.4 °C, "swelling present" from a photo.
**Is not:** a diagnosis, a score, or free text (free text stays on the Signal;
the Observation is the structured extraction).
**Counterexample:** "patient seems anxious" from tone analysis is an
Observation of kind `sentiment`, low confidence — allowed, weighted low, never
a sole trigger.
**Events:** `ObservationRecorded`, `ObservationCorrected`.
**Related:** Signal (source), Finding (interpretation), Evidence (role it
plays when cited).

### 18. Finding — `finding`
**Is:** an engine- or clinician-produced interpretation over Observations:
"day-3 swelling exceeds protocol envelope". Carries the Observation ids it
rests on plus the rule/model version that produced it.
**Is not:** a diagnosis (Providers diagnose; Meridian never does — banned as
an AI output kind) and not an Action (a Finding may *justify* one).
**Events:** `RecoveryDeviationDetected`, `RuleFired`, `FindingNoted`.
**Related:** Risk (aggregated findings), Recommendation (proposed response).

### 19. Risk — `risk`
**Is:** a per-Patient, per-hazard current assessment derived from Findings:
`{hazard, level ∈ {none, watch, high, critical}, basis[]}`. Drives ranking and
routing.
**Is not:** a prediction of certainty, a score shown raw to patients, or a
diagnosis.
**Events:** `RiskLevelChanged` (always cites basis).
**Related:** Recovery Score (one input), Escalation (response to
`high/critical`), Brief (ranking input).

### 20. Recovery Score — `recovery_score`
**Is:** the 0–100 explainable composite for one active care episode
(architecture §3.5): trajectory vs protocol expectation. Recomputed on
relevant Events; every value ships with its penalty breakdown.
**Is not:** a diagnosis, a promise, a cross-patient comparison metric, or a
vanity number — it exists to trigger deviation Findings and inform humans.
**Events:** `RecoveryScoreComputed{score, components[]}`.
**Related:** Observation (inputs), Finding (deviations), Brief (surfacing).

### 21. Evidence
**Is:** the set of Event references cited to justify any claim, Finding,
Recommendation, or ranking. Rendered as tappable citations resolving into the
Timeline.
**Is not:** prose ("based on the patient's history" without ids is not
Evidence — it is banned bluffing, Constitution B2).
**Related:** Confidence (how sure), Explanation = Evidence + reasoning template.

### 22. Confidence — `confidence`
**Is:** the runtime's calibrated certainty in one output, stored as a float
0–1 on the Event, *displayed* only as calibrated bands (`low / moderate /
high`) with basis.
**Is not:** model logits, a guarantee, or something patients see as decimals.
**Related:** Trust (long-run, per action class) vs Confidence (this instance).
Never conflate: Trust gates the ceiling, Confidence picks the floor per act.

### 23. Memory
**Is:** the four defined context stores feeding the Runtime: working
(conversation window), entity (deterministic record assembly), narrative
(LLM-maintained summary, evented as `PatientSummaryUpdated`), procedural
(clinic style/protocol config).
**Is not:** model weights, hidden state, or anything unauditable. If it can't
be printed, it isn't Memory, it's a bug.
**Related:** Evidence (memory claims cite like any other).

---

## Cognition & action

### 24. Intent — `intent`
**Is:** the classified meaning of one human utterance or tap:
`{intent_kind, entities, principal, focus}`. Taps emit pre-parsed Intents;
speech gets classified into them. The unit the Router routes.
**Is not:** the raw text (Signal) or the plan (Runtime output).
**Events:** `IntentClassified` (correlation root for the turn).

### 25. Tool — `tool`
**Is:** one registered, schema-typed capability exposed to the Runtime:
schema + risk class + permissions + compensation + eval suite. The only
doorway from model output to Commands.
**Is not:** an API endpoint, a Python function that happens to exist, or
"function calling" in the abstract. Unregistered = nonexistent.
**Lifecycle:** `proposed → registered (review) → active → deprecated → removed`.
**Related:** Capability (what it grants), Action (its invocation, ledgered).

### 26. Capability — `capability`
**Is:** a permission atom in the authorization lattice
(`scheduling.book`, `records.read`), granted to principals (human roles and
Runtime-per-tier).
**Is not:** a Tool (a Tool *requires* capabilities), a feature flag, or a plan
tier.
**Related:** Tool, Autonomy tier (maps tiers → runtime capabilities).

### 27. Action — `action`
**Is:** one Runtime-initiated state change attempt, wrapped in the Ledger:
proposal (with Evidence, Confidence, risk class, compensation) → gate verdict
→ execution → outcome. Identified by `action_id`, idempotent.
**Is not:** a human's direct Command (not ledgered as Action), a
Recommendation (unexecuted), or a Task (work awaiting a human).
**Lifecycle/states:** `proposed → {auto_approved | awaiting_approval} →
{approved | denied} → {executed | failed} → {clean | undone}`.
**Events:** the Ledger family (§14).
**Related:** Decision, Approval, Trust (consumes outcomes).

### 28. Decision
**Is:** the human judgment point: choosing among options, approving,
denying, or overriding. Every surface exists to serve exactly one Decision
(Constitution I1).
**Is not:** a click (mechanics), a Task (container), or anything the Runtime
does (Runtime acts; only humans decide — P1).
**Events:** `ApprovalGranted/Denied`, `OptionChosen`, `OverrideExercised`.

### 29. Recommendation — `recommendation`
**Is:** a proposed Action or option set presented for a Decision, with
Evidence, Confidence, and trade-offs. A Recommendation is inert until decided.
**Is not:** advice prose; not an Action (nothing executed yet); never clinical
diagnosis.
**Events:** `RecommendationPresented`, resolved by Decision events.

### 30. Approval — `approval`
**Is:** the recorded human grant that releases a specific staged Action
(tier L1/L2): `{action_id, principal, latency_ms, edit_distance}`.
**Is not:** a checkbox ritual (rubber-stamp patterns are down-weighted in
Trust), not consent (patient-side term), not sign-off on tiers (that is
`AutonomyTierChanged`).
**Related:** Action, Trust (its food), Decision (its genus).

### 31. Escalation — `escalation`
**Is:** the Runtime's transfer of a situation to humans with obligation
attached: context bundle + required-by SLA + routing via Care Team. One of
the Runtime's three verbs (act, draft, escalate).
**Is not:** a notification (transport), an FYI, or failure — it is a
first-class outcome (Constitution B7).
**Lifecycle:** `raised → notified → acknowledged → resolved | breached (SLA)`.
**Events:** `EscalationRaised/Acknowledged/Resolved`, `EscalationSlaBreached`.
**Related:** Emergency (highest species), Task (its work container).

### 32. Emergency — `emergency`
**Is:** an Escalation of class emergency: detected red-flag with script-locked
Runtime behavior (LE override) and mandatory notify chain.
**Is not:** anything the Runtime may improvise on; never downgradable by a
model (deterministic layer cannot be suppressed).
**Lifecycle:** `detected → script_engaged → notified → acknowledged → resolved`,
every step timestamped (the chain is the incident report).
**Events:** `EmergencyDetected/Acknowledged/Resolved`, `BreakGlassAccessed`.

### 33. Task — `task`
**Is:** a unit of work awaiting a human, on the Clinic stream: payload,
ranking features, SLA, claim state. What the Brief ranks.
**Is not:** a todo app item, an Action (machine work), or a calendar entry.
**Lifecycle:** `opened → claimed → completed | expired | cancelled`; unclaimed
critical Tasks page.
**Events:** `TaskOpened/Claimed/Completed/Expired`.

### 34. Automation — `automation`
**Is:** a registered standing rule: trigger (Event pattern or schedule) →
Action template + risk class. Config aggregate, versioned, per-Clinic.
**Is not:** ad-hoc cron, hidden behavior, or code — Automations are data,
inspectable and listable ("what will you do on your own?" must be answerable).
**Events:** `AutomationRegistered/Enabled/Disabled/Fired`.
**Related:** Workflow (multi-step), Tool (what it invokes).

### 35. Workflow — `workflow`
**Is:** a durable multi-step orchestration with compensation semantics
(reschedule cascade, escalation ladder) — the Temporal-executed unit.
**Is not:** a UI wizard, a BPMN diagram, or a synonym for "process" in prose.
**Lifecycle:** `started → step_n → {completed | compensated | escalated}`.
**Events:** step-level Events with shared `correlation_id`.

### 36. Trust — `trust`
**Is:** the computed, decaying, per-`(clinic, action_class)` record of earned
autonomy: outcome counters → score → tier (`L0..L3`). Changed only by
evidence + human enactment (promotions) or automatically (demotions).
**Is not:** Confidence (per-instance), a vibe, a setting, or a sales lever.
**Events:** `AutonomyTierChanged{cell, from, to, basis, enacted_by}`.
**Related:** Ledger (input), Action (governed output).

---

## Surface & channels

### 37. Conversation — `conversation`
**Is:** the persistent thread between one principal and Meridian on one
logical counterpart: patient↔clinic (any channel) or staff↔runtime. Channel-
tagged Message events with one `conversation_id`.
**Is not:** a channel (WhatsApp is transport), a session (auth concept), or a
page.
**Lifecycle:** `open` forever by default; `emergency_locked` during
emergencies.
**Events:** `MessageReceived/Sent`, `ConversationEscalated`.

### 38. Morning Brief — `brief`
**Is:** the ranked, precomputed stack of Tasks/cards for one principal at one
moment: THE operating surface. "Brief" alone is the canonical short form.
**Is not:** a dashboard, a report, a digest email, or the alerting path
(emergencies page independently).
**Lifecycle:** `generated → consumed (cards decided) → superseded` (continuous
regeneration; `BriefGenerated` events).
**Related:** Task (items), Card (rendering), Decision (purpose).

### 39. Notification — `notification`
**Is:** one delivery attempt of content to a principal over a channel, chosen
by the router (urgency × preference × time), with delivery state tracked.
Always carries a next Action or Decision.
**Is not:** the Escalation/content itself (transport vs substance); never
purposeless (Constitution #19).
**Lifecycle:** `queued → sent → delivered → read | failed → fallback_channel`.
**Events:** `NotificationQueued/Sent/Delivered/Read/Failed`.

### Card — `card` *(added: required by surface law)*
**Is:** one typed, registry-defined UI unit materialized as an answer or
Decision container (`approval`, `timeline`, `slot_picker`, ...). Models choose
cards + data; code renders.
**Is not:** free-form HTML, a page, or decoration (V2).

### Encounter — `encounter`
**Is:** one bounded episode of direct care: opened when care starts (visit,
teleconsult), closed by the Provider; groups Observations, notes,
prescriptions of that episode.
**Is not:** an Appointment (the *plan* to have an Encounter), a Conversation,
or a billing line.
**Lifecycle:** `opened → in_progress → closed → (note_signed)`.
**Events:** `EncounterOpened/Closed`, `NoteDrafted/NoteSigned`.
**Related:** Appointment (usually precedes), FollowUpPlan (often spawned at
close).

---

## 40. Banned synonyms (CI-enforced)

| Banned | Use instead |
|---|---|
| user (for care recipients) | patient |
| customer, client, lead, contact | patient / organization |
| chart, file, folder, profile (clinical) | patient_record / timeline |
| history | timeline |
| doctor (as code identifier for staff-at-large) | provider / staff |
| appointment slot "inventory" | availability |
| dashboard, home, overview | brief |
| alert (noun, generic) | escalation / notification (pick the real one) |
| audit_log, audit_trail (datastore) | (none — the stream is the audit) |
| bot, assistant, agent (product surface) | Meridian / runtime (internal) |
| AI action "suggestion" | recommendation |
| task (for machine work) | action |
| event (for UI interactions) | intent |
| message (for domain events) | event |
| score (unqualified) | recovery_score / trust / confidence |
| sync, syncing | (name the actual projection/replay) |
| soft delete | (none — events; erasure = crypto-shred) |
| admin (unqualified) | clinic_admin / org_admin |
| session (for conversations) | conversation |
| notification (for escalations) | escalation |

---

*Amendment log*
- v1.0 — ratified alongside Constitution v1.0. 40 entries.
