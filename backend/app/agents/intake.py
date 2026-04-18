"""Intake agent: hand-rolled loop that turns user messages into profile deltas.

Contract with the LLM is strict JSON (see prompts/intake_system.md).
"""
import json
from datetime import datetime
from pathlib import Path

from ..ollama_client import chat

PROMPT_VERSION = "v1"
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "intake_system.md").read_text()

REQUIRED_FIELDS = ["fitness_level", "goals", "injuries", "equipment"]
ALLOWED_FIELDS = {
    "name", "age", "sex", "height_cm", "weight_kg",
    "fitness_level", "goals", "injuries", "conditions",
    "equipment", "notes",
}
INJURY_VOCAB = {
    "left_knee", "right_knee", "lower_back", "upper_back",
    "left_shoulder", "right_shoulder", "left_hip", "right_hip",
    "neck", "left_wrist", "right_wrist", "left_elbow", "right_elbow",
}
EQUIPMENT_VOCAB = {"bodyweight", "dumbbell", "barbell", "machine", "cable"}
FITNESS_LEVELS = {"beginner", "intermediate", "advanced"}
GOALS = {"general_strength", "hypertrophy", "fat_loss", "endurance"}
SEXES = {"male", "female", "other"}


def _parse_json_lenient(text: str) -> dict | None:
    """Find the first { ... } block that parses."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _sanitize_updates(raw: dict) -> tuple[dict, list[str]]:
    """Keep only allowed fields and validate vocab. Returns (clean, warnings)."""
    warnings: list[str] = []
    clean: dict = {}
    if not isinstance(raw, dict):
        return {}, ["profile_updates was not a dict"]
    for k, v in raw.items():
        if k not in ALLOWED_FIELDS:
            warnings.append(f"ignored unknown field: {k}")
            continue
        if k == "fitness_level":
            if v in FITNESS_LEVELS:
                clean[k] = v
            else:
                warnings.append(f"invalid fitness_level: {v!r}")
        elif k == "goals":
            if v in GOALS:
                clean[k] = v
            else:
                warnings.append(f"invalid goals: {v!r}")
        elif k == "sex":
            if v in SEXES:
                clean[k] = v
            else:
                warnings.append(f"invalid sex: {v!r}")
        elif k == "injuries":
            if isinstance(v, list):
                filtered = [x for x in v if x in INJURY_VOCAB]
                dropped = [x for x in v if x not in INJURY_VOCAB]
                if dropped:
                    warnings.append(f"dropped unknown injuries: {dropped}")
                clean[k] = filtered
            else:
                warnings.append("injuries not a list")
        elif k == "equipment":
            if isinstance(v, list):
                filtered = [x for x in v if x in EQUIPMENT_VOCAB]
                dropped = [x for x in v if x not in EQUIPMENT_VOCAB]
                if dropped:
                    warnings.append(f"dropped unknown equipment: {dropped}")
                clean[k] = filtered
            else:
                warnings.append("equipment not a list")
        elif k == "conditions":
            if isinstance(v, list):
                clean[k] = [str(x) for x in v if isinstance(x, (str, int, float))]
            else:
                warnings.append("conditions not a list")
        elif k in ("age",):
            try:
                n = int(v)
                if 0 < n < 130:
                    clean[k] = n
            except Exception:
                warnings.append(f"invalid age: {v!r}")
        elif k in ("height_cm", "weight_kg"):
            try:
                n = float(v)
                if 0 < n < 500:
                    clean[k] = n
            except Exception:
                warnings.append(f"invalid {k}: {v!r}")
        elif k in ("name", "notes"):
            if isinstance(v, str):
                clean[k] = v.strip()
    return clean, warnings


def merge_draft(current: dict, updates: dict) -> dict:
    """List fields replace; scalar fields overwrite when present."""
    out = dict(current or {})
    for k, v in updates.items():
        out[k] = v
    return out


def completeness(draft: dict) -> float:
    """Rough score for UI: fraction of required fields present."""
    present = 0
    for f in REQUIRED_FIELDS:
        val = draft.get(f)
        if val is None:
            continue
        if isinstance(val, list):
            present += 1  # empty list is a valid, confirmed answer
        elif val != "":
            present += 1
    return round(present / len(REQUIRED_FIELDS), 2)


def is_draft_valid_for_finalize(draft: dict) -> tuple[bool, list[str]]:
    """All required fields present AND vocab-valid."""
    missing = []
    for f in REQUIRED_FIELDS:
        if f not in draft:
            missing.append(f)
    return (len(missing) == 0, missing)


def build_chat_history(messages: list, max_turns: int = 20) -> list[dict]:
    """Convert stored IntakeMessage rows to Ollama chat format (last N turns)."""
    out = []
    for m in messages[-max_turns * 2:]:
        if m.role in ("user", "assistant"):
            out.append({"role": m.role, "content": m.content})
    return out


OPENER_TEMPLATE = (
    "Hi! I'm your intake coach — before we build a training plan for you, I'd like to "
    "learn a bit about you. Totally casual: how would you describe your current training "
    "experience — beginner, a few years in, or pretty seasoned?"
)


def initial_opener() -> str:
    return OPENER_TEMPLATE


def run_turn(system_prompt: str, history: list[dict], user_message: str,
             timeout: float = 90.0) -> dict:
    """Single agent turn. Returns a structured payload.

    payload = {
        "assistant_message": str,
        "profile_updates": dict,       # already sanitized
        "red_flag": dict | None,
        "complete": bool,
        "warnings": list[str],
        "raw": str,
        "error": str | None,
    }
    """
    messages = history + [{"role": "user", "content": user_message}]
    text, err = chat(
        system=system_prompt, messages=messages,
        temperature=0.3, force_json=True, timeout=timeout,
    )
    if err:
        return {
            "assistant_message": f"(Intake agent is temporarily unreachable: {err})",
            "profile_updates": {}, "red_flag": None, "complete": False,
            "warnings": [f"ollama error: {err}"], "raw": "", "error": err,
        }

    parsed = _parse_json_lenient(text)
    if parsed is None:
        # one retry with a stricter reminder
        nudge = messages + [
            {"role": "assistant", "content": text or "(unparseable)"},
            {"role": "user", "content": "Your previous reply was not valid JSON. Please reply again with ONLY the JSON object and no other text."},
        ]
        text2, err2 = chat(system=system_prompt, messages=nudge,
                           temperature=0.2, force_json=True, timeout=timeout)
        parsed = _parse_json_lenient(text2) if not err2 else None
        if parsed is None:
            return {
                "assistant_message": "Sorry — I got a bit tangled. Could you rephrase that?",
                "profile_updates": {}, "red_flag": None, "complete": False,
                "warnings": ["unparseable agent output (after retry)"],
                "raw": text, "error": "unparseable",
            }
        text = text2

    msg = str(parsed.get("assistant_message") or "").strip()
    raw_updates = parsed.get("profile_updates") or {}
    updates, warnings = _sanitize_updates(raw_updates)
    red_flag = parsed.get("red_flag") or None
    if red_flag and not isinstance(red_flag, dict):
        red_flag = {"reason": str(red_flag), "area": ""}

    return {
        "assistant_message": msg or "Got it.",
        "profile_updates": updates,
        "red_flag": red_flag,
        "complete": bool(parsed.get("complete")),
        "warnings": warnings,
        "raw": text,
        "error": None,
    }


def stamped_red_flag(flag: dict) -> dict:
    return {**flag, "at": datetime.utcnow().isoformat()}
