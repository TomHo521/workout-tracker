"""Read-only stats + destructive maintenance (export/wipe) endpoints."""
from datetime import date as date_t, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HealthProfile, WorkoutSession, PainLog, Exercise

router = APIRouter(prefix="/stats", tags=["stats"])


# muscle groups we like to nudge about if untrained
TRACKED_GROUPS = ["chest", "back", "legs", "shoulders", "arms", "core"]


def _exercise_index(db: Session) -> dict[str, str]:
    """Map exercise name -> muscle_group (for resolving session entries)."""
    return {e.name: e.muscle_group for e in db.query(Exercise).all()}


@router.get("/streaks")
def streaks(profile_id: int, db: Session = Depends(get_db)):
    """Current streak + last-trained-per-muscle."""
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.profile_id == profile_id)
        .order_by(WorkoutSession.date.desc())
        .all()
    )
    if not sessions:
        return {
            "current_streak_days": 0,
            "total_sessions": 0,
            "last_session_date": None,
            "last_trained": {},
            "nudges": [],
        }

    dates = sorted({s.date for s in sessions}, reverse=True)
    # Current streak: consecutive days ending today or yesterday (rest-day grace of 1)
    today = date_t.today()
    streak = 0
    cursor = today
    dateset = set(dates)
    # allow the streak to start yesterday if today is not logged yet
    if cursor not in dateset and (cursor - timedelta(days=1)) in dateset:
        cursor = cursor - timedelta(days=1)
    while cursor in dateset:
        streak += 1
        cursor -= timedelta(days=1)

    # Last trained per muscle group
    idx = _exercise_index(db)
    last_trained: dict[str, str] = {}
    for s in sessions:
        for entry in (s.entries or []):
            mg = idx.get(entry.get("exercise", ""))
            if mg and mg not in last_trained:
                last_trained[mg] = s.date.isoformat()

    # Nudges: any tracked muscle untrained for > 5 days
    nudges = []
    for mg in TRACKED_GROUPS:
        last = last_trained.get(mg)
        if last is None:
            nudges.append(f"No {mg} training logged yet.")
            continue
        days_ago = (today - date_t.fromisoformat(last)).days
        if days_ago >= 5:
            nudges.append(f"{mg.capitalize()} last trained {days_ago} days ago.")

    return {
        "current_streak_days": streak,
        "total_sessions": len(sessions),
        "last_session_date": dates[0].isoformat(),
        "last_trained": last_trained,
        "nudges": nudges,
    }


@router.get("/export")
def export_all(profile_id: int, db: Session = Depends(get_db)):
    """Full JSON dump of a user's data (profile, sessions, pain log)."""
    p = db.query(HealthProfile).get(profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.profile_id == profile_id)
        .order_by(WorkoutSession.date.asc())
        .all()
    )
    pains = (
        db.query(PainLog)
        .filter(PainLog.profile_id == profile_id)
        .order_by(PainLog.date.asc())
        .all()
    )
    return {
        "exported_at": date_t.today().isoformat(),
        "profile": {
            "id": p.id, "name": p.name, "age": p.age, "sex": p.sex,
            "height_cm": p.height_cm, "weight_kg": p.weight_kg,
            "fitness_level": p.fitness_level, "goals": p.goals,
            "injuries": p.injuries or [], "conditions": p.conditions or [],
            "equipment": p.equipment or [], "notes": p.notes or "",
        },
        "sessions": [
            {
                "id": s.id, "date": s.date.isoformat(),
                "day_label": s.day_label, "entries": s.entries or [],
                "perceived_effort": s.perceived_effort,
                "session_notes": s.session_notes,
                "ai_suggestions": s.ai_suggestions or {},
            } for s in sessions
        ],
        "pain_logs": [
            {
                "id": pl.id, "date": pl.date.isoformat(),
                "area": pl.area, "score": pl.score, "notes": pl.notes,
            } for pl in pains
        ],
    }


@router.delete("/wipe")
def wipe_profile_data(profile_id: int, db: Session = Depends(get_db)):
    """Delete sessions + pain logs for a profile (keeps the profile itself)."""
    p = db.query(HealthProfile).get(profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    db.query(WorkoutSession).filter(WorkoutSession.profile_id == profile_id).delete()
    db.query(PainLog).filter(PainLog.profile_id == profile_id).delete()
    db.commit()
    return {"ok": True}


# ---- M2: analytics helpers ----

def _epley_1rm(weight: float, reps: int) -> float:
    if reps <= 0 or weight <= 0:
        return 0.0
    return round(weight * (1 + reps / 30.0), 1)


@router.get("/volume")
def weekly_volume(profile_id: int, weeks: int = 8, db: Session = Depends(get_db)):
    """Weekly tonnage (reps * weight) per muscle group for the last N weeks."""
    since = date_t.today() - timedelta(weeks=weeks)
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.profile_id == profile_id, WorkoutSession.date >= since)
        .order_by(WorkoutSession.date.asc())
        .all()
    )
    idx = _exercise_index(db)
    # week key: ISO year-week (Monday)
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for s in sessions:
        iso_year, iso_week, _ = s.date.isocalendar()
        wk = f"{iso_year}-W{iso_week:02d}"
        for entry in (s.entries or []):
            mg = idx.get(entry.get("exercise", ""))
            if not mg:
                continue
            for st in entry.get("sets", []):
                reps = int(st.get("reps", 0) or 0)
                w = float(st.get("weight_kg", 0) or 0)
                buckets[wk][mg] += reps * w
    return {
        "weeks": sorted(buckets.keys()),
        "data": {wk: dict(groups) for wk, groups in buckets.items()},
    }


@router.get("/one-rm")
def one_rm_trend(profile_id: int, exercise: str | None = None, db: Session = Depends(get_db)):
    """Per-session best Epley 1RM estimate. Returns one series per exercise."""
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.profile_id == profile_id)
        .order_by(WorkoutSession.date.asc())
        .all()
    )
    series: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        for entry in (s.entries or []):
            name = entry.get("exercise", "")
            if exercise and name != exercise:
                continue
            best = 0.0
            for st in entry.get("sets", []):
                reps = int(st.get("reps", 0) or 0)
                w = float(st.get("weight_kg", 0) or 0)
                best = max(best, _epley_1rm(w, reps))
            if best > 0:
                series[name].append({"date": s.date.isoformat(), "e1rm": best})
    return {"series": dict(series)}


@router.get("/progression")
def suggested_weights(profile_id: int, db: Session = Depends(get_db)):
    """For each exercise the user has logged, suggest next-session top-set weight.

    Rule (simple, conservative):
      - find the last session that included the lift
      - top set = max weight; top_reps = reps on that set
      - if top_rpe <= 7 AND top_reps >= 8  -> +2.5kg
      - if top_rpe >= 9 OR top_reps < 5    -> -2.5kg (deload hint)
      - else                                -> same
      - pain modifier: if any pain>=5 recorded in last 3 days for a related area
        (heuristic: lower_back => squat/deadlift/row/RDL; shoulder => press/bench/pull),
        cap the suggestion at "same" (no increase).
    """
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.profile_id == profile_id)
        .order_by(WorkoutSession.date.desc())
        .all()
    )
    since = date_t.today() - timedelta(days=3)
    recent_pain = (
        db.query(PainLog)
        .filter(PainLog.profile_id == profile_id, PainLog.date >= since, PainLog.score >= 5)
        .all()
    )
    pain_areas = {pl.area for pl in recent_pain}

    def painful(exercise_name: str) -> bool:
        n = exercise_name.lower()
        if "lower_back" in pain_areas and any(k in n for k in ["squat", "deadlift", "row", "rdl", "back extension"]):
            return True
        if ("left_shoulder" in pain_areas or "right_shoulder" in pain_areas) and any(
            k in n for k in ["press", "bench", "pull-up", "pullup", "push-up", "pushup", "overhead"]
        ):
            return True
        if ("left_knee" in pain_areas or "right_knee" in pain_areas) and any(
            k in n for k in ["squat", "lunge", "leg press"]
        ):
            return True
        return False

    seen: dict[str, dict] = {}
    for s in sessions:
        for entry in (s.entries or []):
            name = entry.get("exercise", "")
            if not name or name in seen:
                continue
            top = max(entry.get("sets", []) or [{}], key=lambda st: float(st.get("weight_kg", 0) or 0), default=None)
            if not top or not top.get("weight_kg"):
                continue
            w = float(top["weight_kg"])
            reps = int(top.get("reps", 0) or 0)
            rpe = top.get("rpe")
            rpe = int(rpe) if rpe is not None else None

            if rpe is not None and rpe <= 7 and reps >= 8:
                delta = 2.5
                reason = f"Last top set: {reps}×{w}kg @ RPE {rpe} — progress +2.5kg."
            elif (rpe is not None and rpe >= 9) or reps < 5:
                delta = -2.5
                reason = f"Last top set: {reps}×{w}kg" + (f" @ RPE {rpe}" if rpe is not None else "") + " — deload -2.5kg."
            else:
                delta = 0.0
                reason = f"Last top set: {reps}×{w}kg" + (f" @ RPE {rpe}" if rpe is not None else "") + " — hold weight."

            if delta > 0 and painful(name):
                delta = 0.0
                reason += " Pain flagged in related area — holding weight."

            seen[name] = {
                "last_weight_kg": w,
                "last_reps": reps,
                "last_rpe": rpe,
                "suggested_weight_kg": max(0.0, round(w + delta, 2)),
                "delta_kg": delta,
                "reason": reason,
                "last_date": s.date.isoformat(),
            }
    return {"suggestions": seen, "pain_areas_recent": sorted(pain_areas)}
