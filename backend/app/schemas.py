from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    fitness_level: str = "beginner"
    goals: str = "general_strength"
    injuries: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=lambda: ["bodyweight", "dumbbell", "barbell"])
    notes: str = ""


class ProfileOut(ProfileIn):
    id: int
    updated_at: datetime

    class Config:
        from_attributes = True


class ExerciseOut(BaseModel):
    id: int
    name: str
    muscle_group: str
    equipment: str
    default_sets: int
    default_reps: str
    notes: str
    youtube_url: str = ""

    class Config:
        from_attributes = True


class PainLogIn(BaseModel):
    profile_id: int
    date: date
    area: str
    score: int = Field(ge=0, le=10)
    notes: str = ""


class PainLogOut(BaseModel):
    id: int
    profile_id: int
    date: date
    area: str
    score: int
    notes: str

    class Config:
        from_attributes = True


class ProgramDay(BaseModel):
    label: str
    focus: str
    exercises: list[ExerciseOut]


class Program(BaseModel):
    profile_id: int
    profile_name: str
    split: str
    days: list[ProgramDay]


class SetEntry(BaseModel):
    reps: int
    weight_kg: float = 0.0
    rpe: Optional[int] = None


class ExerciseEntry(BaseModel):
    exercise: str
    sets: list[SetEntry]
    notes: str = ""


class SessionIn(BaseModel):
    profile_id: int
    date: date
    day_label: str = ""
    entries: list[ExerciseEntry]
    perceived_effort: int = 5
    session_notes: str = ""


class SessionOut(BaseModel):
    id: int
    profile_id: int
    date: date
    day_label: str
    entries: list[ExerciseEntry]
    perceived_effort: int
    session_notes: str
    ai_suggestions: dict
    created_at: datetime

    class Config:
        from_attributes = True
