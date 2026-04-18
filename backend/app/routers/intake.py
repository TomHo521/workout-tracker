from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import IntakeSession, IntakeMessage, HealthProfile
from ..schemas import (
    IntakeSessionOut, IntakeMessageOut, IntakeMessageIn,
    ProfileOut,
)
from ..agents.intake import (
    SYSTEM_PROMPT, PROMPT_VERSION,
    build_chat_history, run_turn, initial_opener,
    merge_draft, completeness, is_draft_valid_for_finalize,
    stamped_red_flag,
)

router = APIRouter(prefix="/intake", tags=["intake"])


def _flag_attrs(s: IntakeSession) -> None:
    """SQLAlchemy with JSON columns needs explicit attribute assignment to detect mutation."""
    s.profile_draft = dict(s.profile_draft or {})
    s.red_flags = list(s.red_flags or [])


@router.post("/start", response_model=IntakeSessionOut)
def start_intake(db: Session = Depends(get_db)):
    s = IntakeSession(
        status="in_progress",
        model_used="llama3.1:8b",
        prompt_version=PROMPT_VERSION,
        disclaimer_accepted_at=datetime.utcnow(),
        profile_draft={},
        red_flags=[],
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    # canned opener — saves an LLM call on start
    db.add(IntakeMessage(session_id=s.id, role="assistant", content=initial_opener()))
    db.commit()
    db.refresh(s)
    return s


@router.get("/{session_id}", response_model=IntakeSessionOut)
def get_intake(session_id: int, db: Session = Depends(get_db)):
    s = db.query(IntakeSession).get(session_id)
    if not s:
        raise HTTPException(404, "intake session not found")
    return s


@router.get("/{session_id}/messages", response_model=list[IntakeMessageOut])
def get_messages(session_id: int, db: Session = Depends(get_db)):
    return (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == session_id)
        .order_by(IntakeMessage.id.asc())
        .all()
    )


@router.post("/{session_id}/message")
def post_message(session_id: int, body: IntakeMessageIn, db: Session = Depends(get_db)):
    s = db.query(IntakeSession).get(session_id)
    if not s:
        raise HTTPException(404, "intake session not found")
    if s.status in ("complete", "abandoned"):
        raise HTTPException(400, f"session is {s.status}")

    user_text = (body.content or "").strip()
    if not user_text:
        raise HTTPException(400, "empty message")

    _flag_attrs(s)

    # store user message
    db.add(IntakeMessage(session_id=session_id, role="user", content=user_text))
    db.commit()

    # rebuild history from DB (ensures we include the message we just saved)
    all_msgs = (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == session_id)
        .order_by(IntakeMessage.id.asc())
        .all()
    )
    # history for the LLM excludes the just-added user message (run_turn appends it)
    history_rows = [m for m in all_msgs if m.id != all_msgs[-1].id]
    history = build_chat_history(history_rows)

    result = run_turn(SYSTEM_PROMPT, history, user_text)

    # merge draft
    if result["profile_updates"]:
        s.profile_draft = merge_draft(s.profile_draft, result["profile_updates"])

    # handle red flag (additive)
    if result["red_flag"]:
        s.red_flags = [*s.red_flags, stamped_red_flag(result["red_flag"])]
        s.status = "escalated"

    s.completeness_score = completeness(s.profile_draft)
    s.agent_ready_to_finalize = 1 if result["complete"] else 0

    # store assistant message
    db.add(IntakeMessage(
        session_id=session_id, role="assistant",
        content=result["assistant_message"],
        tool_args={"profile_updates": result["profile_updates"]},
        tool_result={"warnings": result["warnings"], "raw": result["raw"]},
    ))
    db.commit()
    db.refresh(s)

    return {
        "assistant_message": result["assistant_message"],
        "profile_draft": s.profile_draft,
        "completeness_score": s.completeness_score,
        "red_flags": s.red_flags,
        "status": s.status,
        "agent_ready_to_finalize": bool(s.agent_ready_to_finalize),
        "warnings": result["warnings"],
    }


@router.post("/{session_id}/finalize", response_model=ProfileOut)
def finalize_intake(session_id: int, db: Session = Depends(get_db)):
    """Persist the intake draft as a real HealthProfile."""
    s = db.query(IntakeSession).get(session_id)
    if not s:
        raise HTTPException(404, "intake session not found")
    if s.status == "escalated":
        raise HTTPException(400, "session was escalated — cannot finalize into a profile")
    if s.status == "complete":
        raise HTTPException(400, "session already finalized")

    ok, missing = is_draft_valid_for_finalize(s.profile_draft or {})
    if not ok:
        raise HTTPException(400, f"profile missing required fields: {missing}")

    draft = dict(s.profile_draft or {})

    # Upsert onto existing profile if session linked, else create a new one.
    p: HealthProfile | None = None
    if s.profile_id:
        p = db.query(HealthProfile).get(s.profile_id)
    if p is None:
        p = HealthProfile(
            name=draft.get("name") or "Athlete",
            fitness_level=draft.get("fitness_level") or "beginner",
            goals=draft.get("goals") or "general_strength",
            injuries=draft.get("injuries") or [],
            equipment=draft.get("equipment") or ["bodyweight"],
            conditions=draft.get("conditions") or [],
            age=draft.get("age"),
            sex=draft.get("sex"),
            height_cm=draft.get("height_cm"),
            weight_kg=draft.get("weight_kg"),
            notes=draft.get("notes") or "",
        )
        db.add(p)
    else:
        for k in ("name", "fitness_level", "goals", "injuries", "equipment",
                  "conditions", "age", "sex", "height_cm", "weight_kg", "notes"):
            if k in draft:
                setattr(p, k, draft[k])

    s.status = "complete"
    s.finalized_at = datetime.utcnow()

    db.commit()
    db.refresh(p)
    s.profile_id = p.id
    db.commit()
    return p
