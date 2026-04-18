from datetime import date as date_t
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HealthProfile, WorkoutSession
from ..schemas import SessionIn, SessionOut
from ..ollama_client import generate_suggestions

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _profile_dict(p: HealthProfile) -> dict:
    return {
        "name": p.name, "age": p.age, "sex": p.sex,
        "height_cm": p.height_cm, "weight_kg": p.weight_kg,
        "fitness_level": p.fitness_level, "goals": p.goals,
        "injuries": p.injuries or [], "conditions": p.conditions or [],
        "equipment": p.equipment or [], "notes": p.notes or "",
    }


def _session_to_dict(s: WorkoutSession) -> dict:
    return {
        "date": s.date.isoformat(),
        "day_label": s.day_label,
        "entries": s.entries or [],
        "perceived_effort": s.perceived_effort,
        "session_notes": s.session_notes,
    }


@router.get("", response_model=list[SessionOut])
def list_sessions(profile_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(WorkoutSession).order_by(WorkoutSession.date.desc())
    if profile_id:
        q = q.filter(WorkoutSession.profile_id == profile_id)
    return q.all()


@router.get("/calendar")
def calendar(year: int, month: int, profile_id: int | None = None, db: Session = Depends(get_db)):
    """Return sessions for a given month, grouped by ISO date string."""
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")
    start = date_t(year, month, 1)
    end = date_t(year + 1, 1, 1) if month == 12 else date_t(year, month + 1, 1)
    q = db.query(WorkoutSession).filter(
        WorkoutSession.date >= start, WorkoutSession.date < end
    )
    if profile_id:
        q = q.filter(WorkoutSession.profile_id == profile_id)
    sessions = q.order_by(WorkoutSession.date.asc(), WorkoutSession.id.asc()).all()
    days: dict[str, list[dict]] = {}
    for s in sessions:
        key = s.date.isoformat()
        days.setdefault(key, []).append({
            "id": s.id,
            "day_label": s.day_label or "",
            "entries_count": len(s.entries or []),
            "perceived_effort": s.perceived_effort,
            "has_suggestions": bool((s.ai_suggestions or {}).get("summary")),
        })
    return {"year": year, "month": month, "days": days}


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(WorkoutSession).get(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.post("", response_model=SessionOut)
def create_session(data: SessionIn, db: Session = Depends(get_db)):
    p = db.query(HealthProfile).get(data.profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    s = WorkoutSession(
        profile_id=data.profile_id,
        date=data.date,
        day_label=data.day_label,
        entries=[e.model_dump() for e in data.entries],
        perceived_effort=data.perceived_effort,
        session_notes=data.session_notes,
        ai_suggestions={},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.post("/{session_id}/suggest", response_model=SessionOut)
def suggest(session_id: int, db: Session = Depends(get_db)):
    s = db.query(WorkoutSession).get(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    p = db.query(HealthProfile).get(s.profile_id)
    suggestions = generate_suggestions(_profile_dict(p), _session_to_dict(s))
    s.ai_suggestions = suggestions
    db.commit()
    db.refresh(s)
    return s


@router.get("/by-date/{on_date}", response_model=list[SessionOut])
def by_date(on_date: date_t, profile_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(WorkoutSession).filter(WorkoutSession.date == on_date)
    if profile_id:
        q = q.filter(WorkoutSession.profile_id == profile_id)
    return q.all()
