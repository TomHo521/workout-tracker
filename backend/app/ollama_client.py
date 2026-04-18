"""Thin wrapper for local Ollama (llama3.1) suggestions."""
import json
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b"

SYSTEM = (
    "You are a knowledgeable strength-and-conditioning coach. "
    "You give concise, safe, practical suggestions grounded in the athlete's "
    "health profile (injuries, conditions) and their workout history. "
    "Always respect contraindications. Respond ONLY with valid JSON."
)

PROMPT_TEMPLATE = """\
Health profile:
{profile}

Today's workout session ({date}, {day_label}):
{session}

Perceived effort: {rpe}/10
Session notes: {notes}

Task: Produce JSON with this schema:
{{
  "summary": "2-3 sentence recap of today's session quality",
  "next_session": ["3 specific, actionable recommendations for the next workout"],
  "watchouts": ["injury/health-specific cautions relevant to this athlete"],
  "recovery": "1-2 sentences on recovery/mobility focus for the next 24-48h"
}}
Output JSON only. No prose before or after.
"""


WEEKLY_PROMPT_TEMPLATE = """\
Health profile:
{profile}

Recent pain log (last 7 days):
{pain}

Last 7 days of sessions:
{sessions}

Trends you should consider:
- Total tonnage per muscle group
- Days since each muscle group was trained
- Any pain score >= 5 near a lift

Task: Produce JSON with this schema:
{{
  "summary": "3-5 sentence review of the week",
  "what_worked": ["2-4 specific wins"],
  "concerns": ["2-4 specific concerns, injury- or fatigue-related"],
  "next_week_plan": ["3-5 concrete adjustments for next week"],
  "program_changes": ["Any specific exercise swaps you would recommend, and why"]
}}
Output JSON only. No prose before or after.
"""


def _build_prompt(profile: dict, session: dict) -> str:
    return PROMPT_TEMPLATE.format(
        profile=json.dumps(profile, indent=2),
        date=session.get("date"),
        day_label=session.get("day_label") or "",
        session=json.dumps(session.get("entries", []), indent=2),
        rpe=session.get("perceived_effort", 5),
        notes=session.get("session_notes") or "(none)",
    )


def _call_ollama(prompt: str, timeout: float) -> tuple[str, str | None]:
    """Returns (text, error). error is None on success."""
    payload = {
        "model": MODEL,
        "system": SYSTEM,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(OLLAMA_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return "", str(e)
    return (data.get("response") or "").strip(), None


def _parse_json_or_fallback(text: str, fallback: dict) -> dict:
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(text[start:end + 1])
            parsed.setdefault("raw", text)
            return parsed
    except Exception:
        pass
    fb = {**fallback, "summary": text[:400], "raw": text}
    return fb


def generate_suggestions(profile: dict, session: dict, timeout: float = 120.0) -> dict:
    prompt = _build_prompt(profile, session)
    text, err = _call_ollama(prompt, timeout)
    if err:
        return {"summary": f"(Ollama unreachable: {err})",
                "next_session": [], "watchouts": [], "recovery": "", "raw": ""}
    return _parse_json_or_fallback(text, {
        "summary": "", "next_session": [], "watchouts": [], "recovery": "",
    })


def generate_weekly_review(profile: dict, pain: list[dict], sessions: list[dict], timeout: float = 180.0) -> dict:
    prompt = WEEKLY_PROMPT_TEMPLATE.format(
        profile=json.dumps(profile, indent=2),
        pain=json.dumps(pain, indent=2) if pain else "(none)",
        sessions=json.dumps(sessions, indent=2) if sessions else "(none)",
    )
    text, err = _call_ollama(prompt, timeout)
    if err:
        return {"summary": f"(Ollama unreachable: {err})",
                "what_worked": [], "concerns": [], "next_week_plan": [], "program_changes": [], "raw": ""}
    return _parse_json_or_fallback(text, {
        "summary": "", "what_worked": [], "concerns": [],
        "next_week_plan": [], "program_changes": [],
    })
