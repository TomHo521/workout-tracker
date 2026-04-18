from datetime import date as date_t, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HealthProfile, WorkoutSession, PainLog
from ..ollama_client import generate_weekly_review

router = APIRouter(prefix="/review", tags=["review"])


def _profile_dict(p: HealthProfile) -> dict:
    return {
        "name": p.name, "age": p.age, "sex": p.sex,
        "height_cm": p.height_cm, "weight_kg": p.weight_kg,
        "fitness_level": p.fitness_level, "goals": p.goals,
        "injuries": p.injuries or [], "conditions": p.conditions or [],
        "equipment": p.equipment or [], "notes": p.notes or "",
    }


@router.post("/weekly")
def weekly_review(profile_id: int, db: Session = Depends(get_db)):
    p = db.query(HealthProfile).get(profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    since = date_t.today() - timedelta(days=7)
    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.profile_id == profile_id, WorkoutSession.date >= since)
        .order_by(WorkoutSession.date.asc())
        .all()
    )
    pain = (
        db.query(PainLog)
        .filter(PainLog.profile_id == profile_id, PainLog.date >= since)
        .order_by(PainLog.date.asc())
        .all()
    )
    s_payload = [
        {
            "date": s.date.isoformat(),
            "day_label": s.day_label,
            "perceived_effort": s.perceived_effort,
            "entries": s.entries or [],
            "session_notes": s.session_notes,
        } for s in sessions
    ]
    pain_payload = [
        {"date": pl.date.isoformat(), "area": pl.area, "score": pl.score, "notes": pl.notes}
        for pl in pain
    ]
    result = generate_weekly_review(_profile_dict(p), pain_payload, s_payload)
    return {
        "profile_id": profile_id,
        "window_start": since.isoformat(),
        "window_end": date_t.today().isoformat(),
        "sessions_count": len(s_payload),
        "pain_entries_count": len(pain_payload),
        "ai_review": result,
    }
