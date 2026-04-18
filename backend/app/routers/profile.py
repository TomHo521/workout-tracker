from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import HealthProfile
from ..schemas import ProfileIn, ProfileOut

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(HealthProfile).order_by(HealthProfile.id).all()


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    p = db.query(HealthProfile).get(profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    return p


@router.post("", response_model=ProfileOut)
def create_profile(data: ProfileIn, db: Session = Depends(get_db)):
    p = HealthProfile(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: int, data: ProfileIn, db: Session = Depends(get_db)):
    p = db.query(HealthProfile).get(profile_id)
    if not p:
        raise HTTPException(404, "profile not found")
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p
