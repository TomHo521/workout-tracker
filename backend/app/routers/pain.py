from datetime import date as date_t, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PainLog
from ..schemas import PainLogIn, PainLogOut

router = APIRouter(prefix="/pain", tags=["pain"])


@router.get("", response_model=list[PainLogOut])
def list_pain(profile_id: int, days: int = 30, db: Session = Depends(get_db)):
    since = date_t.today() - timedelta(days=days)
    return (
        db.query(PainLog)
        .filter(PainLog.profile_id == profile_id, PainLog.date >= since)
        .order_by(PainLog.date.desc(), PainLog.id.desc())
        .all()
    )


@router.post("", response_model=PainLogOut)
def create_pain(data: PainLogIn, db: Session = Depends(get_db)):
    entry = PainLog(**data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{pain_id}")
def delete_pain(pain_id: int, db: Session = Depends(get_db)):
    p = db.query(PainLog).get(pain_id)
    if not p:
        raise HTTPException(404, "pain entry not found")
    db.delete(p)
    db.commit()
    return {"ok": True}
