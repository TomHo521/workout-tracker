"""Trainer endpoints.

Phase D-stub: `propose` runs the deterministic program generator, wraps the
output as a ProgramDraft with a per-exercise rationale, and runs the safety
validator. Approve/reject flip the draft state. Once approved, the active
program (GET /program/{profile_id}) is this draft; older drafts are superseded.

An LLM-backed trainer agent can replace the generation step later without
changing the endpoints or the approval flow.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HealthProfile, Exercise, ProgramDraft
from ..schemas import ProgramDraftOut
from ..program import build_program
from ..safety.validate import validate_program_against_profile

router = APIRouter(prefix="/trainer", tags=["trainer"])


class ProposeIn(BaseModel):
    profile_id: int
    intake_session_id: int | None = None


def _exercise_catalog(db: Session) -> dict[str, dict]:
    return {
        e.name: {
            "contraindicated_for": list(e.contraindicated_for or []),
            "equipment": e.equipment or "bodyweight",
        }
        for e in db.query(Exercise).all()
    }


def _rationale_for_exercise(ex: dict, profile: HealthProfile) -> str:
    injuries = set(profile.injuries or [])
    contra = set(ex.get("contraindicated_for") or [])
    equipment = ex.get("equipment", "")
    bits = []
    bits.append(f"{ex['muscle_group']} · {equipment}")
    if injuries and contra and not (contra & injuries):
        related = {"lower_back": "back", "left_knee": "knee", "right_knee": "knee",
                   "left_shoulder": "shoulder", "right_shoulder": "shoulder"}
        tags = {related.get(i, i) for i in injuries}
        if tags:
            bits.append(f"chosen to avoid {', '.join(sorted(tags))} stress")
    if profile.fitness_level == "beginner":
        bits.append("beginner-friendly movement")
    return "; ".join(bits) + "."


@router.post("/propose", response_model=ProgramDraftOut)
def propose(data: ProposeIn, db: Session = Depends(get_db)):
    p = db.query(HealthProfile).get(data.profile_id)
    if not p:
        raise HTTPException(404, "profile not found")

    # 1) generate candidate program deterministically (library-only)
    program_payload = build_program(db, p)
    # enrich exercises in the payload with contraindicated_for so the validator can resolve
    name_to_ex = {e.name: e for e in db.query(Exercise).all()}
    for day in program_payload.get("days", []):
        for ex in day["exercises"]:
            src = name_to_ex.get(ex["name"])
            if src is not None:
                ex["contraindicated_for"] = list(src.contraindicated_for or [])

    # 2) build a per-exercise rationale
    rationale: dict[str, str] = {}
    for day in program_payload.get("days", []):
        for ex in day["exercises"]:
            rationale.setdefault(ex["name"], _rationale_for_exercise(ex, p))

    # 3) run the safety validator (same catalog as above)
    catalog = _exercise_catalog(db)
    report = validate_program_against_profile(
        program_payload,
        profile_injuries=list(p.injuries or []),
        profile_equipment=list(p.equipment or []),
        exercise_catalog=catalog,
    )

    draft = ProgramDraft(
        profile_id=p.id,
        source_intake_session_id=data.intake_session_id,
        status="pending" if report.ok else "rejected",
        payload=program_payload,
        rationale=rationale,
        validator_report=report.to_dict(),
        reject_reason="" if report.ok else "failed safety validator",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@router.get("/drafts", response_model=list[ProgramDraftOut])
def list_drafts(profile_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ProgramDraft)
        .filter(ProgramDraft.profile_id == profile_id)
        .order_by(ProgramDraft.id.desc())
        .all()
    )


@router.get("/drafts/{draft_id}", response_model=ProgramDraftOut)
def get_draft(draft_id: int, db: Session = Depends(get_db)):
    d = db.query(ProgramDraft).get(draft_id)
    if not d:
        raise HTTPException(404, "draft not found")
    return d


@router.post("/drafts/{draft_id}/approve", response_model=ProgramDraftOut)
def approve_draft(draft_id: int, db: Session = Depends(get_db)):
    d = db.query(ProgramDraft).get(draft_id)
    if not d:
        raise HTTPException(404, "draft not found")
    if d.status == "rejected":
        raise HTTPException(400, f"cannot approve a rejected draft: {d.reject_reason}")
    # supersede prior approvals for this profile
    db.query(ProgramDraft).filter(
        ProgramDraft.profile_id == d.profile_id,
        ProgramDraft.status == "approved",
    ).update({"status": "pending"})
    d.status = "approved"
    d.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(d)
    return d


@router.post("/drafts/{draft_id}/reject", response_model=ProgramDraftOut)
def reject_draft(draft_id: int, reason: str = "", db: Session = Depends(get_db)):
    d = db.query(ProgramDraft).get(draft_id)
    if not d:
        raise HTTPException(404, "draft not found")
    d.status = "rejected"
    d.reject_reason = reason or "user rejected"
    db.commit()
    db.refresh(d)
    return d


@router.get("/active/{profile_id}")
def active_program(profile_id: int, db: Session = Depends(get_db)):
    """Returns the currently-approved draft for this profile, or 404 if none."""
    d = (
        db.query(ProgramDraft)
        .filter(ProgramDraft.profile_id == profile_id, ProgramDraft.status == "approved")
        .order_by(ProgramDraft.approved_at.desc())
        .first()
    )
    if not d:
        raise HTTPException(404, "no approved draft for this profile")
    return {"draft_id": d.id, "payload": d.payload, "rationale": d.rationale,
            "approved_at": d.approved_at.isoformat() if d.approved_at else None}
