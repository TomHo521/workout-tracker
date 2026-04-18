from sqlalchemy import Column, Integer, String, Float, Date, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class HealthProfile(Base):
    __tablename__ = "health_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    sex = Column(String)
    height_cm = Column(Float)
    weight_kg = Column(Float)
    fitness_level = Column(String, default="beginner")  # beginner/intermediate/advanced
    goals = Column(String, default="general_strength")
    injuries = Column(JSON, default=list)       # e.g. ["left_knee", "lower_back"]
    conditions = Column(JSON, default=list)     # e.g. ["hypertension"]
    equipment = Column(JSON, default=list)      # e.g. ["barbell","dumbbell","bodyweight"]
    notes = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    muscle_group = Column(String, nullable=False)  # chest, back, legs, shoulders, arms, core, full_body
    equipment = Column(String, default="bodyweight")
    contraindicated_for = Column(JSON, default=list)  # list of injury tags this exercise should avoid
    default_sets = Column(Integer, default=3)
    default_reps = Column(String, default="8-12")
    notes = Column(String, default="")
    youtube_url = Column(String, default="")


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("health_profiles.id"), nullable=False)
    date = Column(Date, nullable=False)
    day_label = Column(String, default="")          # e.g. "Day A - Upper"
    entries = Column(JSON, default=list)            # [{exercise, sets:[{reps, weight_kg, rpe}], notes}]
    perceived_effort = Column(Integer, default=5)   # 1-10
    session_notes = Column(String, default="")
    ai_suggestions = Column(JSON, default=dict)     # { summary, next_session, watchouts }
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("HealthProfile")


class PainLog(Base):
    __tablename__ = "pain_logs"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("health_profiles.id"), nullable=False)
    date = Column(Date, nullable=False)
    area = Column(String, nullable=False)   # e.g. "lower_back", "left_knee"
    score = Column(Integer, default=0)      # 0-10
    notes = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
