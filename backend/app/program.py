"""Injury-aware full-body program generator."""
from sqlalchemy.orm import Session

from .models import Exercise, HealthProfile


# Templates by fitness level. Each day: (label, focus, [muscle_group picks])
TEMPLATES = {
    "beginner": [
        ("Day A - Full Body",   "full_body", ["legs","chest","back","core"]),
        ("Day B - Full Body",   "full_body", ["legs","shoulders","back","core"]),
        ("Day C - Full Body",   "full_body", ["legs","chest","back","arms"]),
    ],
    "intermediate": [
        ("Day A - Upper",       "upper",     ["chest","back","shoulders","arms"]),
        ("Day B - Lower",       "lower",     ["legs","legs","core"]),
        ("Day C - Upper",       "upper",     ["back","chest","shoulders","arms"]),
        ("Day D - Lower",       "lower",     ["legs","core","core"]),
    ],
    "advanced": [
        ("Day A - Push",        "push",      ["chest","shoulders","arms"]),
        ("Day B - Pull",        "pull",      ["back","back","arms"]),
        ("Day C - Legs",        "legs",      ["legs","legs","core"]),
        ("Day D - Upper",       "upper",     ["chest","back","shoulders"]),
        ("Day E - Lower",       "lower",     ["legs","core"]),
    ],
}


def _safe_exercises(db: Session, muscle_group: str, profile: HealthProfile) -> list[Exercise]:
    """Return exercises for a muscle group that don't clash with injuries or missing equipment."""
    injuries = set(profile.injuries or [])
    equipment = set(profile.equipment or [])
    q = db.query(Exercise).filter(Exercise.muscle_group == muscle_group).all()
    result = []
    for ex in q:
        contra = set(ex.contraindicated_for or [])
        if contra & injuries:
            continue
        if equipment and ex.equipment not in equipment and ex.equipment != "bodyweight":
            # allow if bodyweight is in equipment anyway
            continue
        result.append(ex)
    return result


def build_program(db: Session, profile: HealthProfile) -> dict:
    level = (profile.fitness_level or "beginner").lower()
    template = TEMPLATES.get(level, TEMPLATES["beginner"])
    split = "full_body" if level == "beginner" else ("upper_lower" if level == "intermediate" else "PPL+UL")

    days = []
    for label, focus, picks in template:
        picked: list[Exercise] = []
        used_ids: set[int] = set()
        for mg in picks:
            candidates = [e for e in _safe_exercises(db, mg, profile) if e.id not in used_ids]
            if not candidates:
                continue
            ex = candidates[0]
            picked.append(ex)
            used_ids.add(ex.id)
        days.append({
            "label": label,
            "focus": focus,
            "exercises": [
                {
                    "id": e.id, "name": e.name, "muscle_group": e.muscle_group,
                    "equipment": e.equipment, "default_sets": e.default_sets,
                    "default_reps": e.default_reps, "notes": e.notes,
                } for e in picked
            ],
        })

    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "split": split,
        "days": days,
    }
