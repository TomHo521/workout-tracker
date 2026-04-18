from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HealthProfile, ProgramDraft
from ..program import build_program

router = APIRouter(prefix="/program", tags=["program"])


@router.get("/{profile_id}")
def get_program(profile_id: int, db: Session = Depends(get_db)):
    p = db.query(HealthProfile).get(profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    # Prefer an approved trainer draft if one exists.
    approved = (
        db.query(ProgramDraft)
        .filter(ProgramDraft.profile_id == profile_id, ProgramDraft.status == "approved")
        .order_by(ProgramDraft.approved_at.desc())
        .first()
    )
    if approved and approved.payload:
        return approved.payload
    return build_program(db, p)
