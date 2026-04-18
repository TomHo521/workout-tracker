from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Exercise
from ..schemas import ExerciseOut

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseOut])
def list_exercises(muscle_group: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Exercise).order_by(Exercise.muscle_group, Exercise.name)
    if muscle_group:
        q = q.filter(Exercise.muscle_group == muscle_group)
    return q.all()
