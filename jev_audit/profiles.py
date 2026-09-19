from __future__ import annotations

import json
from pathlib import Path

from .models import AuditProfile, AuditRule


BUNDLED_PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


def available_profiles() -> list[str]:
    if not BUNDLED_PROFILE_DIR.exists():
        return []
    return sorted(path.stem for path in BUNDLED_PROFILE_DIR.glob("*.json"))


def load_profile(name_or_path: str) -> AuditProfile:
    candidate = Path(name_or_path)
    if candidate.exists():
        path = candidate.resolve()
    else:
        path = BUNDLED_PROFILE_DIR / f"{name_or_path}.json"

    if not path.exists():
        known = ", ".join(available_profiles()) or "(none)"
        raise FileNotFoundError(f"Audit profile not found: {name_or_path!r}. bundled={known}")

    data = json.loads(path.read_text(encoding="utf-8"))
    rules = tuple(
        AuditRule(
            id=str(item["id"]),
            title=str(item["title"]),
            description=str(item["description"]),
        )
        for item in data["rules"]
    )

    status_criteria = {str(k): str(v) for k, v in data["status_criteria"].items()}
    required_statuses = {"clear", "review", "rework", "unknown"}
    if set(status_criteria) != required_statuses:
        raise ValueError(
            "status_criteria must contain exactly: clear, review, rework, unknown"
        )

    return AuditProfile(
        name=str(data["name"]),
        description=str(data.get("description", "")),
        rules=rules,
        status_criteria=status_criteria,
    )
