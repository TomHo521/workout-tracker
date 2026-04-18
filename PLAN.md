# Workout Tracker — Product & Engineering Plan

> Living document. Aspirations first (what we want to be), implementation later.
> Last updated: 2026-04-18

---

## 1. Vision

A strength-training app that treats the user as an individual with a body — injuries, asymmetries, good days and bad — not a generic avatar following a generic program. The app should feel like a knowledgeable training partner who remembers what happened last week, knows what hurts, and adjusts the plan accordingly.

**One-line pitch:** *The only workout tracker that makes the program safer the more you use it.*

---

## 2. Who it's for

**Primary**: intermediate lifters (1–5 years training) with at least one nagging injury or limitation who are tired of pausing generic programs to manually substitute exercises.

**Secondary**: returning lifters post-injury / post-surgery who want rehab-aware programming, and beginners who don't want to accidentally hurt themselves.

**Not for (yet)**: competitive powerlifters chasing peak meets, bodybuilders on prep, CrossFit/Olympic lifting specialists. Those are vertical expansions after we nail general strength.

---

## 3. Positioning & differentiators

Most trackers are either **loggers** (Strong, Hevy — great UX, dumb about you) or **program apps** (Juggernaut AI, Fitbod — smart, but injury-blind). Our wedge is the intersection: a *logging-quality* UX that is *injury-aware end-to-end*.

Three things no major competitor does well:

1. **Contraindication-driven exercise selection.** The exercise library itself knows what to avoid for which injury. This already exists in the v0 codebase.
2. **Pain-weighted progression.** Weight increases slow or reverse when the user reports pain in a related body part, automatically. No other consumer app does this.
3. **Local-LLM-backed coaching.** Private-by-default AI review of your training, no data leaves the device unless the user opts into a cloud model.

---

## 4. Product pillars (aspirations)

### 4.1 The workout itself feels like an app, not a form
- Rest timer that auto-starts on set complete, with sound and haptic.
- Big, thumb-friendly steppers for weight and reps. One-handed operation.
- Plate calculator (per barbell weight) inline.
- Voice logging for hands-free entry between sets.
- Exercise demo (YouTube link short-term, licensed video long-term).
- Offline-first. Gym Wi-Fi is a lie.

### 4.2 The program progresses on its own
- Auto weight progression based on last session's RPE and rep completion.
- Deload triggers after 2 stalled sessions or a pain spike.
- Estimated 1RM (Epley) tracked over time per lift.
- Weekly volume per muscle group, with a soft cap to prevent junk volume.
- Program variants: full-body / upper-lower / push-pull-legs, selectable by level.

### 4.3 The AI coach is useful, not decorative
- Per-session suggestions (already shipped, v0).
- **Weekly review**: aggregates 7 days of sessions + pain logs → structured recommendations for next week.
- **Program adjustments**: when a lift stalls or pain spikes, the coach proposes a swap and explains why.
- **Safety guardrails**: the coach is never allowed to recommend a contraindicated exercise. This is enforced in code, not prompt.
- Privacy-first: runs against local Ollama by default. Cloud-LLM is an opt-in upgrade.

### 4.4 Injury and recovery are first-class citizens
- Daily pain log (0–10 per body part) as its own entity, not buried in notes.
- Rehab mode: lower loads, prescribed tempo, PT-style exercises.
- "Pain trends" chart overlaid with training load.
- Profile evolves: recovery, new injuries, new equipment — program regenerates.

### 4.5 Retention loops
- Streaks ("you've logged 12 sessions in a row").
- Nudges ("you haven't trained legs in 6 days").
- PR notifications ("new 5-rep max on deadlift").
- Weekly summary pushed to the user every Sunday.

### 4.6 Analytics the user actually looks at
- Volume per muscle per week.
- Estimated 1RM curve per main lift.
- Bodyweight over time (optional HealthKit/Google Fit sync).
- Pain-vs-load overlay.

### 4.7 Trust & compliance
- Medical disclaimer on first run.
- Privacy policy in-app.
- Data export (full JSON) and wipe.
- Age gate (13+).
- No dark patterns.

---

## 5. Phased roadmap

> Milestones, not deadlines. Each milestone is a demoable slice.

### M0 — v0 (shipped 2026-04-18)
- Health profile, injury-aware program generation, per-session logging, per-session Ollama suggestions, clickable month calendar.
- Stack: FastAPI + SQLite + vanilla JS, local Ollama `llama3.1:8b`.
- Single user, local-only.

### M1 — "Feels like a real app" (this is the next slice)
- Rest timer + set-complete sound/haptic.
- Thumb-sized steppers, plate calculator.
- Daily pain log (backend + UI).
- Streaks and nudges in header.
- Medical disclaimer modal on first run.
- Data export (JSON) and wipe.
- Exercise YouTube-link field.

### M2 — "Feels smart"
- Auto-progression engine (RPE + completion → next weight).
- Estimated 1RM per lift (Epley) with a line chart.
- Weekly volume-per-muscle chart.
- Weekly AI review endpoint (7-day rollup → Ollama).
- Pain-aware progression: pain entries > 4 in an area slow/reverse progression on related lifts.

### M3 — "Feels shippable" (PWA launch)
- PWA manifest + service worker, installable on iOS/Android home screen.
- Offline-first DB via IndexedDB (mirror of server SQLite).
- Voice logging (Web Speech API).
- Onboarding flow: profile → goals → equipment → optional injury survey → first program generated.
- Privacy policy and T&Cs.

### M4 — "Multi-user and in the cloud"
- Auth (Supabase or Clerk — TBD).
- Cloud sync of profile, sessions, pain log.
- Free tier (log + basic AI) vs. paid (unlimited AI, weekly reviews, analytics).
- Stripe.

### M5 — "Native & in the stores"
- Capacitor shell over the PWA.
- HealthKit / Google Fit integration for bodyweight, HR, sleep.
- Push notifications (APNs / FCM).
- Apple App Store & Google Play submission.

### M6 — "Defensible"
- Licensed exercise video library.
- Rehab protocols (physio-reviewed).
- Optional cloud-LLM tier (frontier model, user-paid).
- Program marketplace / sharing.

---

## 6. Non-goals (explicitly out of scope)

- Nutrition tracking. Every fitness app does this badly; we won't.
- Cardio-first training. We are a strength app first. Conditioning is a later addition.
- Social feed. Maybe a share-card export; not a timeline.
- Gamification (badges, points, leveling). Streaks are enough.
- AI-generated exercises. The library is curated and safety-tagged; the AI picks from it.

---

## 7. Guiding principles

1. **Safety over novelty.** If we have to choose between a cool feature and an injury-safe default, safety wins.
2. **Logging is sacred.** If the logging flow gets slower, the feature is wrong.
3. **The AI is a coach, not a DJ.** It gives grounded, specific advice from the user's own data. It does not hallucinate programs.
4. **Local-first, cloud-optional.** The app works fully offline, on-device. Cloud is an enhancement, never a requirement.
5. **Ship small, visible slices.** Every milestone is a thing the user can touch, not a refactor.

---

## 8. Open questions

- How much of the program logic lives in the LLM vs. in deterministic code? Current bias: **safety and progression in code, narrative and adjustments in LLM.** Revisit after M2.
- Do we ship a free tier with cloud sync, or only cloud sync on paid? Leaning paid-only (cost control).
- Capacitor vs. React Native rewrite for M5? Capacitor ships faster; RN is more native-feeling. Decide when PWA metrics justify native.
- Who reviews our rehab protocols? Must be a licensed PT before we call anything "rehab." Until then, "pain-aware training" is the safer framing.

---

## 9. Success metrics (later, but worth naming)

- **Activation**: % of new users who log ≥ 3 sessions in their first week.
- **Retention**: % of users still logging at week 4.
- **AI engagement**: % of sessions where the user requests a suggestion.
- **Safety signal**: % of users whose pain score trends down over 8 weeks (vs. steady or up).
- **NPS** from injured/returning lifters specifically — that's the wedge.
