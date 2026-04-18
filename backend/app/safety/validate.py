"""Deterministic validator for a ProgramDraft payload against a HealthProfile.

Pure Python, no LLM. This is the safety moat — any proposed program must pass
this before it reaches the user.

Program payload shape (same as program.build_program output):
    {
      "profile_id": int, "profile_name": str, "split": str,
      "days": [
        {"label": str, "focus": str, "exercises": [
            {"id": int, "name": str, "muscle_group": str,
             "equipment": str, "default_sets": int, "default_reps": str, "notes": str},
            ...
        ]},
        ...
      ],
    }
"""
from dataclasses import dataclass, field


@dataclass
class Violation:
    exercise: str
    reason: str
    day_label: str = ""


@dataclass
class ValidationReport:
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "violations": [v.__dict__ for v in self.violations],
            "warnings": list(self.warnings),
        }


def validate_program_against_profile(
    payload: dict,
    profile_injuries: list[str],
    profile_equipment: list[str],
    exercise_catalog: dict[str, dict],
) -> ValidationReport:
    """Check program payload against the user's profile and the authoritative catalog.

    exercise_catalog: {name: {"contraindicated_for": [...], "equipment": "..."}}
    """
    injuries = set(profile_injuries or [])
    equipment = set(profile_equipment or [])
    violations: list[Violation] = []
    warnings: list[str] = []

    days = payload.get("days") or []
    if not days:
        warnings.append("program has no days")
        return ValidationReport(ok=False, violations=[], warnings=warnings)

    seen_names: set[str] = set()
    for day in days:
        label = day.get("label", "")
        exercises = day.get("exercises") or []
        if not exercises:
            warnings.append(f"day '{label}' has no exercises")
            continue
        for ex in exercises:
            name = ex.get("name", "").strip()
            if not name:
                violations.append(Violation("(unnamed)", "exercise missing name", label))
                continue
            seen_names.add(name)
            catalog_entry = exercise_catalog.get(name)
            if catalog_entry is None:
                violations.append(Violation(name, "exercise not in authoritative library", label))
                continue
            contra = set(catalog_entry.get("contraindicated_for") or [])
            clash = contra & injuries
            if clash:
                violations.append(Violation(
                    name,
                    f"contraindicated for injury tag(s): {sorted(clash)}",
                    label,
                ))
            eq = catalog_entry.get("equipment") or "bodyweight"
            if equipment and eq not in equipment and eq != "bodyweight":
                violations.append(Violation(
                    name, f"requires equipment not in profile: {eq}", label,
                ))

    if not seen_names:
        warnings.append("no exercises across all days")

    return ValidationReport(ok=(len(violations) == 0), violations=violations, warnings=warnings)


# ---------- inline self-tests (run with `python -m app.safety.validate`) ----------

def _self_test() -> None:
    catalog = {
        "Barbell Back Squat": {"contraindicated_for": ["lower_back", "left_knee"], "equipment": "barbell"},
        "Goblet Squat":       {"contraindicated_for": ["left_knee"],               "equipment": "dumbbell"},
        "Push-up":            {"contraindicated_for": [],                          "equipment": "bodyweight"},
        "Bench Press":        {"contraindicated_for": ["left_shoulder"],           "equipment": "barbell"},
    }
    good = {
        "days": [{"label": "A", "focus": "full", "exercises": [
            {"name": "Push-up"}, {"name": "Goblet Squat"},
        ]}]
    }
    bad_injury = {
        "days": [{"label": "A", "focus": "full", "exercises": [
            {"name": "Barbell Back Squat"},
        ]}]
    }
    bad_equipment = {
        "days": [{"label": "A", "focus": "full", "exercises": [
            {"name": "Bench Press"},
        ]}]
    }
    bad_unknown = {
        "days": [{"label": "A", "focus": "full", "exercises": [
            {"name": "Zercher Atlas Carry"},
        ]}]
    }

    r = validate_program_against_profile(good, ["lower_back"], ["bodyweight", "dumbbell"], catalog)
    assert r.ok, f"expected ok: {r.to_dict()}"

    r = validate_program_against_profile(bad_injury, ["lower_back"], ["barbell"], catalog)
    assert not r.ok and any("lower_back" in v.reason for v in r.violations), r.to_dict()

    r = validate_program_against_profile(bad_equipment, [], ["bodyweight"], catalog)
    assert not r.ok and any("requires equipment" in v.reason for v in r.violations), r.to_dict()

    r = validate_program_against_profile(bad_unknown, [], ["bodyweight"], catalog)
    assert not r.ok and any("not in authoritative library" in v.reason for v in r.violations), r.to_dict()

    print("safety.validate: all self-tests passed")


if __name__ == "__main__":
    _self_test()
