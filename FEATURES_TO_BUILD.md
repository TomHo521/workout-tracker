# Features To Build — AI Intake + Trainer Agent

> Implementation plan for the conversational onboarding + agentic programming system described in PLAN.md §4.4 and the intake/trainer conversation. This file is execution-focused: what to build, in what order, how to verify it.
>
> Owner: —
> Status: draft
> Last updated: 2026-04-18

---

## Goal

Replace the static Profile form (or complement it) with a two-agent system:

1. **Intake agent** — conversational, empathetic; extracts structured `HealthProfile` fields through dialogue.
2. **Trainer agent** — structured-output; proposes a `ProgramDraft` from a finalized profile, drawing only from the curated exercise library and respecting contraindications in *code*, not just in prompt.

The resulting program lands on a human-review screen before it replaces the current program.

---

## What already exists (and is reused)

- `HealthProfile` model (injuries, conditions, equipment, goals, fitness_level) — target of intake extraction.
- `Exercise` library with `contraindicated_for` tags — authoritative safety data.
- `program.build_program` — current deterministic generator; becomes the *fallback* and the *schema* for what the trainer agent emits.
- `ollama_client` — local LLM plumbing; extended, not replaced.
- Medical disclaimer (M1) — gates intake start.

Nothing built here should remove or break the existing Profile form — it stays as an escape hatch for expert users.

---

## Architecture

```
┌──────────────────────┐      ┌────────────────────────┐
│  Onboarding chat UI  │◄────►│  /intake/message (SSE) │
└──────────┬───────────┘      └──────────┬─────────────┘
           │ profile preview              │
           ▼                              ▼
┌──────────────────────┐      ┌────────────────────────┐
│ ProfileDraft + diffs │      │  Intake agent loop     │
└──────────┬───────────┘      │  - LLM call            │
           │ finalize          │  - parse tool calls    │
           ▼                   │  - validate schema     │
┌──────────────────────┐      │  - persist deltas      │
│   /trainer/propose   │──────┤  - stream reply        │
└──────────┬───────────┘      └────────────────────────┘
           ▼
┌──────────────────────┐      ┌────────────────────────┐
│  ProgramDraft review │◄────►│  Contraindication      │
│  (approve / tweak)   │      │  validator (code)      │
└──────────────────────┘      └────────────────────────┘
```

---

## Phased delivery

Each phase produces a demoable slice. Do not start phase N+1 until N has acceptance criteria met.

### Phase A — Data model foundations

**Backend**

- [ ] `IntakeSession` table
  - `id, profile_id (nullable until finalized), status (in_progress|complete|abandoned), started_at, finalized_at, completeness_score (0–1), model_used, disclaimer_accepted_at`
- [ ] `IntakeMessage` table
  - `id, session_id, role (user|assistant|system|tool), content, tool_name, tool_args (JSON), tool_result (JSON), created_at`
- [ ] `ProfileFieldProvenance` table
  - `id, session_id, field_name, value (JSON), source_message_id, confidence (0–1), confirmed_by_user (bool)`
- [ ] `ProgramDraft` table
  - `id, profile_id, source_intake_session_id (nullable), status (pending|approved|rejected), payload (JSON — same shape as `build_program` output), rationale (JSON — per-exercise reason), created_at, approved_at`
- [ ] Migrations wired into `migrate.py`.

**Acceptance**: schemas exist; rows can be inserted via SQLAlchemy in an ad-hoc script; `stats/export` includes the new tables.

**Risk**: over-designing provenance too early. If it feels heavy, skip `ProfileFieldProvenance` in Phase A and add in Phase H.

---

### Phase B — Intake agent loop (hand-rolled)

**Backend**

- [ ] `agents/intake.py`
  - System prompt: intake coach persona, explicit "you do not prescribe exercises" rule, red-flag triage instructions.
  - Tool schema (function-calling style):
    - `set_profile_field(field, value, confidence)` — value typed per field
    - `ask_followup(topic)` — optional self-annotation
    - `flag_red_flag(reason, area)` — escalates to triage path
    - `mark_complete()` — agent believes intake is done
  - Hand-rolled loop: LLM call → parse JSON tool calls → validate against schema → persist diffs → echo assistant text back to client.
- [ ] Validation layer (pydantic) for every tool call. Invalid → re-prompt once, then log and skip.
- [ ] Resumable sessions — GET `/intake/{id}` returns full transcript + current profile draft.

**Endpoints**

- [ ] `POST /intake/start` → creates `IntakeSession`, returns opener message
- [ ] `POST /intake/{id}/message` → streams assistant response via **SSE**
- [ ] `GET /intake/{id}` → transcript + current draft
- [ ] `POST /intake/{id}/finalize` → writes `HealthProfile`, sets session status, returns profile id

**Frontend**

- [ ] New `/onboarding` view (chat UI): message list, streaming tokens, right-sidebar live profile preview (editable inline).
- [ ] "Start fresh" vs "use form" split on first run.
- [ ] Quick-reply chips when agent asks common yes/no or enum questions.

**Acceptance**: a new user can converse with the agent, see their profile draft fill in live, edit any field inline, and finalize into a real `HealthProfile`. Works with local `llama3.1:8b`.

**Risk**: local model reliability for tool-use. Mitigation: strict JSON-only prompts, pydantic validation, one retry on parse failure. If pass rate < 90% on Phase F fixtures, escalate to hybrid (Phase G) sooner.

---

### Phase C — Deterministic contraindication validator

This is the safety moat. Pure code, no LLM.

**Backend**

- [ ] `safety/validate.py`
  - `validate_program_against_profile(program: ProgramDraftPayload, profile: HealthProfile) -> ValidationReport`
  - Walks every exercise, checks `contraindicated_for ∩ profile.injuries == ∅`.
  - Also checks: all exercises exist in the library, equipment is in profile's available list.
  - Returns `{ok: bool, violations: [{exercise, reason}]}`.
- [ ] Unit tests with synthetic profiles (lower_back, bilateral knee, shoulder impingement) + a known-bad program.

**Wire-in**

- [ ] `POST /trainer/propose` (Phase D) must call validator; on failure, either re-prompt the trainer with the violations or fall back to `build_program`.

**Acceptance**: every `ProgramDraft` that reaches the frontend has passed the validator. Attempting to approve an unvalidated draft is impossible at the API level.

---

### Phase D — Trainer agent + ProgramDraft review

**Backend**

- [ ] `agents/trainer.py`
  - Input context: finalized profile + the **pre-filtered** exercise library (only exercises compatible with injuries + equipment). This constrains the model to safe picks before it even starts.
  - Tool schema:
    - `propose_program(days: [{label, focus, exercises: [{exercise_id, sets, reps, rationale}]}])`
  - Post-generation: run validator from Phase C. On violation → re-prompt with error list (max 2 retries), then fall back to `build_program`.

**Endpoints**

- [ ] `POST /trainer/propose` — takes `profile_id`, optional `intake_session_id`; returns a `ProgramDraft` with `status=pending`.
- [ ] `GET /program-drafts/{id}` — fetch a draft.
- [ ] `POST /program-drafts/{id}/approve` — sets status; this draft becomes the source for `GET /program/{profile_id}`.
- [ ] `POST /program-drafts/{id}/reject` — flag + store reason; profile stays on whatever was previous.

**Frontend**

- [ ] `ProgramDraft` review screen: per-day cards, each exercise card shows the agent's **rationale** ("picked goblet squat over back squat because of your lower-back tightness") and a "swap" button that re-runs the trainer for that slot only.
- [ ] Approve → becomes active program → routed to Today view.

**Acceptance**: finalizing an intake produces a reviewable draft within ~10s on a warm Ollama; user can approve and see it appear in Today.

---

### Phase E — Red-flag triage

**Backend**

- [ ] Explicit red-flag list in code (chest pain during exercise, recent surgery < 6 weeks, pregnancy without clearance, suspected eating disorder language, under-13, syncope). Keep it short and conservative.
- [ ] When the intake agent emits `flag_red_flag`, the session transitions to `status=escalated`, the agent's follow-up is suppressed, and the UI shows a "please speak to a healthcare professional before proceeding" card with a link to user-supplied resources.
- [ ] Also run a **second-pass classifier** on each user message independently of the agent (belt + suspenders). Minimal: keyword regex → LLM confirmation. Any hit forces `escalated`.

**Frontend**

- [ ] Escalation card; Profile/Today are gated until the user acknowledges.

**Acceptance**: test fixtures containing each red flag all reach `escalated` state without a program ever being generated.

---

### Phase F — Eval fixtures and regression harness

**Backend**

- [ ] `evals/fixtures/` — 20–30 synthetic user stories as YAML:
  ```
  name: returning_from_acl
  conversation_plan: [...]          # scripted user turns
  expected_profile:
    injuries: [left_knee]
    fitness_level: intermediate
  expected_program_must_not_include: [Barbell Back Squat, Walking Lunge]
  expected_red_flag: false
  ```
- [ ] `evals/run.py` — replays each fixture against a live app instance, asserts extracted profile ⊇ expected, and that the approved program does not contain forbidden exercises.
- [ ] Run on CI (later) and before each release.

**Acceptance**: ≥ 90% fixture pass rate on local `llama3.1:8b`. Failing fixtures block a release.

**Risk**: this is the most-skipped but most-important phase. Don't let it slip.

---

### Phase G — Hybrid model toggle

**Backend**

- [ ] Config: `INTAKE_MODEL` and `TRAINER_MODEL` env vars, each independently `ollama://llama3.1:8b` or `anthropic://claude-sonnet-4-6` or `openai://gpt-4.1`.
- [ ] Pluggable `LLMClient` interface; Ollama, Anthropic, OpenAI adapters.
- [ ] Rerun Phase F evals on each backend; publish pass rates in a markdown table in the repo.

**Frontend**

- [ ] Settings toggle: "Use local model only" (default on for privacy) vs "Use cloud model for intake and programming" (shows which provider).
- [ ] Explicit privacy copy inside the toggle.

**Acceptance**: toggling changes which backend answers, with no other behavioral change. Evals pass on both paths.

---

### Phase H — Provenance, editing, re-onboarding

**Backend**

- [ ] Populate `ProfileFieldProvenance` during Phase B (if deferred).
- [ ] `GET /profile/{id}/provenance` — per-field source message + confidence.
- [ ] Re-onboarding flow: new `IntakeSession` seeded with current profile, agent asks "what's changed?" rather than starting from zero.

**Frontend**

- [ ] Hovering any field on the Profile view shows provenance popover: *"You mentioned this on April 18th: 'my left knee acts up on lunges.'"*
- [ ] "Something changed" button opens a lightweight re-onboarding chat.

**Acceptance**: every field in a profile that came through intake has provenance; every manual edit is also recorded (source=user_edit).

---

## Cross-cutting concerns

### Streaming transport

- Prefer SSE (simpler, one-way) over WebSockets. FastAPI supports it via `StreamingResponse`.
- Frontend: `EventSource` with a fetch fallback for POST-with-body streaming.

### Prompt management

- System prompts live in `agents/prompts/intake_system.md` and `trainer_system.md`, not inline. Review-able in PRs.
- Version prompts (`v1`, `v2`) and record which version produced each session — lets us A/B and roll back.

### Observability

- Log token counts, latency, retry counts per LLM call.
- Transcript review queue: first 100 real onboardings flagged for human review before further changes.

### Legal / compliance

- Stronger disclaimer specifically in the chat context; surfaced at intake start AND in the system prompt.
- Transcript retention: default 90 days; user-triggered delete always available.
- Age gate (13+) before intake can start.
- Agent must never output "diagnose," "prescribe," or specific medication language; post-hoc string filter belt-and-suspenders.

---

## Open decisions

1. **Model for intake/trainer**: start local only, or go hybrid from day one?
   - Lean: start local, build Phase F evals alongside Phase B, decide on hybrid based on actual pass rates.
2. **Program mutability**: is the approved program immutable until re-onboarding, or can the user swap single exercises ad hoc on Today?
   - Lean: ad hoc swaps allowed but logged; re-onboarding rewrites the whole draft.
3. **Orchestration library**: keep hand-rolled through Phase D, or adopt PydanticAI / LangGraph early?
   - Lean: hand-rolled until we have three agents or >2 tool retries per turn on average. Don't pay for abstractions we're not using.
4. **Where does the red-flag classifier run?** Same model as intake, or a separate small model?
   - Lean: same model with a separate one-shot system prompt; upgrade to a dedicated classifier only if false-negative rate is > 2% on fixtures.

---

## Non-goals for this plan

- Licensed video exercise demos.
- Live 1-on-1 human-coach escalation. The escalation target is the *user's own healthcare provider*, not an in-app coach.
- Program marketplace or sharing (deferred to M6 in PLAN.md).
- Fine-tuning. We are prompt + tool-use only; if we need to fine-tune, the architecture changes and this doc is rewritten.

---

## Definition of done

A new user can:

1. Accept the disclaimer.
2. Have a 5–15 minute chat with the intake agent.
3. Watch their profile fill in live, with any field editable.
4. Finalize, see the trainer propose a program with per-exercise rationale.
5. Approve or tweak the program.
6. Begin logging sessions against it that same day.

…and throughout the process, no contraindicated exercise ever reaches their screen as a recommendation, red flags route to professional referral, and the user's transcript is visible, editable, and deletable.
