# CLAUDE.md

Guidance for Claude Code (and future Claude sessions) working in this repo.

---

## Project

Personal workout tracker with injury-aware programming and a local-LLM coach. Single-user today; multi-user + cloud planned in later milestones.

- **PLAN.md** — vision, product pillars, phased roadmap M0 → M6, non-goals. Aspirational.
- **FEATURES_TO_BUILD.md** — concrete execution plan for the AI intake + trainer agent system (phased A–H with acceptance criteria).
- **README**: none yet (intentional — docs live in the two files above).

Read PLAN.md for *what we're building and why*; read FEATURES_TO_BUILD.md for *how the next major slice lands*.

---

## Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite (`backend/workout.db`). Python 3.12, venv at `./venv`.
- **Frontend**: vanilla HTML / CSS / JS served as static files by FastAPI from `/frontend`. No bundler, no framework — intentional for now.
- **LLM**: local Ollama at `http://localhost:11434/api/generate`, model `llama3.1:8b`.
- **No build step.** Edit files, refresh browser.

---

## Run

```bash
source venv/bin/activate
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

Open `http://127.0.0.1:8765/`. First run shows a medical disclaimer (stored in localStorage).

Stop: `pkill -f "uvicorn app.main:app"`.

---

## Repo layout

```
backend/
  app/
    main.py            FastAPI app, CORS, static mount, router wiring
    database.py        SQLAlchemy engine + Base + get_db
    models.py          HealthProfile, Exercise, WorkoutSession, PainLog
    schemas.py         Pydantic I/O models
    seed.py            Exercise library seed (contraindication-tagged)
    program.py         Deterministic injury-aware program generator
    ollama_client.py   Local-LLM wrappers (per-session + weekly review)
    migrate.py         Lightweight SQLite ALTER-TABLE migrations
    routers/
      profile.py       CRUD on health profile
      program.py       GET /program/{profile_id}
      sessions.py      Workout sessions + calendar + per-session AI suggest
      exercises.py     Exercise library read
      pain.py          Pain log CRUD
      stats.py         Streaks, volume, e1RM, progression, export, wipe
      review.py        Weekly AI review (7-day rollup → Ollama)
frontend/
  index.html           All view templates
  app.js               All views, steppers, rest timer, charts, disclaimer
  styles.css
PLAN.md
FEATURES_TO_BUILD.md
CLAUDE.md              (this file)
requirements.txt
venv/
```

---

## Core data model

- `HealthProfile` — age, sex, metrics, fitness_level, goals, **injuries** (list of tags), conditions, equipment.
- `Exercise` — library entry with `muscle_group`, `equipment`, `contraindicated_for` (list of injury tags), `youtube_url`.
- `WorkoutSession` — one daily worksheet: `entries` (JSON list of `{exercise, sets:[{reps, weight_kg, rpe}], notes}`), `perceived_effort`, `session_notes`, `ai_suggestions` (populated on-demand).
- `PainLog` — `{date, area, score 0-10, notes}` per profile.

Injury safety is driven by `Exercise.contraindicated_for`. Any generator or suggestion surface must respect it in code, not prompt.

---

## Architectural conventions

1. **Safety in code, narrative in LLM.** The contraindication filter, progression rules, and validator belong in Python. The LLM summarizes, explains, and suggests — it does *not* decide what is safe.
2. **Library-only exercise selection.** The LLM chooses from `Exercise` rows; it does not invent moves.
3. **Local-first.** All data in SQLite; Ollama called locally. Cloud-anything is opt-in, arrives in M4+.
4. **No bundler / no framework on the frontend (for now).** Vanilla JS with template tags. Moving to a framework is a deliberate M3+ decision, not a drift.
5. **Ollama is unreliable; assume it.** `ollama_client.py` must return a valid-shaped dict even on network failure — UIs rely on the shape, not the success.

---

## Adding things

### A new endpoint
- Add router file under `backend/app/routers/` (or extend existing).
- Register in `backend/app/main.py`.
- Reload is automatic with `--reload`.

### A new exercise
- Append to `EXERCISES` in `backend/app/seed.py`. Include `contraindicated_for` tags — this is the safety contract.
- Re-seed is idempotent (existing rows are left alone; missing `youtube_url` backfills).

### A schema migration
- Add logic to `backend/app/migrate.py` (PRAGMA-guarded `ALTER TABLE`). Called on startup before `create_all`.

### A new view
- Add `<template id="tpl-foo">` to `frontend/index.html`.
- Add `renderFoo()` in `frontend/app.js` and map it in `switchView`.
- Add a nav button with `data-view="foo"`.

### Prompting changes
- Edit `PROMPT_TEMPLATE` / `WEEKLY_PROMPT_TEMPLATE` in `backend/app/ollama_client.py`.
- The system prompt and schema are enforced there; frontends trust the shape.

---

## What's shipped (M0–M2)

- Health profile CRUD; injury- and equipment-aware program generator.
- Daily worksheet logging with steppers, rest timer, set-complete beep, plate calculator.
- Month calendar history view; per-session AI suggestions on demand.
- Daily pain log feeding progression + AI.
- Streak badge and "haven't trained X in N days" nudges.
- Auto-progression suggestion (RPE + completion heuristic, pain-aware).
- Weekly volume per muscle group + e1RM line charts (inline SVG).
- Weekly AI review (7-day rollup).
- Data export (JSON) and wipe.
- Medical disclaimer modal on first run.
- YouTube demo link per exercise.

---

## What's next

- **M3 (PWA)**: manifest + service worker, offline shell, voice logging, onboarding flow.
- **AI intake + trainer agent** — see FEATURES_TO_BUILD.md. This is the big architectural expansion.
- **M4+ (cloud)**: auth, sync, tiers — requires external accounts.

---

## Style

- No emojis in code unless the user asks. No decorative comments.
- Comments explain *why* when non-obvious. Never narrate *what*.
- Keep new abstractions minimal. Three similar lines beat a premature helper.
- Python: type hints on public functions. Pydantic for I/O.
- JS: no frameworks, no bundler, no TypeScript — yet.

---

## Gotchas

- `/sessions/{session_id}` has `session_id: int`. Any literal sub-path (`/sessions/calendar`, `/sessions/by-date/...`) **must be declared before** the int-typed route, or FastAPI rejects `"calendar"` as an int with 422.
- `workout.db` is the single source of truth. Deleting it loses data but is a quick reset; seeding is idempotent.
- Ollama model tag is the full `llama3.1:8b` — bare `llama3.1` 404s.
- `pip` in this repo is 24.0 inside venv; upgrade is optional and noisy.

---

## For future Claude sessions

- Check memory at `~/.claude/projects/<this-dir-slug>/memory/MEMORY.md` for user preferences and project history.
- Don't create new `.md` files without explicit ask (exceptions: user explicitly asked for PLAN.md, FEATURES_TO_BUILD.md, this CLAUDE.md).
- Prefer editing existing files to adding new ones.
- When in doubt about scope or architecture, read PLAN.md first, then FEATURES_TO_BUILD.md.
