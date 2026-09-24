from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import AuditProfile, AuditRule


BUNDLED_PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


def available_profiles() -> list[str]:
    if not BUNDLED_PROFILE_DIR.exists():
        return []
    return sorted(path.stem for path in BUNDLED_PROFILE_DIR.glob("*.json"))


def load_profile(name_or_path: str) -> AuditProfile:
    raw = str(name_or_path).strip()
    if not raw:
        raise ValueError("profile name or JSON path must not be empty")

    # A bundled profile name is a trust-boundary identifier. Resolve it before
    # looking at the caller's working directory so a target repository cannot
    # replace `development` or another built-in policy by path shadowing.
    if raw in available_profiles():
        path = BUNDLED_PROFILE_DIR / f"{raw}.json"
    else:
        candidate = Path(raw).expanduser()
        if candidate.exists() and candidate.is_dir():
            raise ValueError(f"Audit profile path must be a JSON file, not a directory: {candidate}")
        if candidate.suffix.lower() == ".json" or candidate.is_absolute() or candidate.parent != Path("."):
            path = candidate.resolve()
        else:
            path = BUNDLED_PROFILE_DIR / f"{raw}.json"

    if not path.exists():
        known = ", ".join(available_profiles()) or "(none)"
        raise FileNotFoundError(f"Audit profile not found: {name_or_path!r}. bundled={known}")
    if not path.is_file():
        raise ValueError(f"Audit profile path must be a JSON file: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Audit profile is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("Audit profile root must be a JSON object")

    profile_name = data.get("name")
    if not isinstance(profile_name, str) or not profile_name.strip():
        raise ValueError("Audit profile name must be a non-empty string")

    description = data.get("description", "")
    if not isinstance(description, str):
        raise ValueError("Audit profile description must be a string")

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("Audit profile rules must be a list")
    parsed_rules: list[AuditRule] = []
    rule_ids: set[str] = set()
    for index, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            raise ValueError(f"Audit profile rule #{index + 1} must be an object")
        values = {key: item.get(key) for key in ("id", "title", "description")}
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise ValueError(
                f"Audit profile rule #{index + 1} requires non-empty string id/title/description"
            )
        if values["id"] in rule_ids:
            raise ValueError(f"Audit profile rule id is duplicated: {values['id']}")
        rule_ids.add(values["id"])
        parsed_rules.append(
            AuditRule(
                id=values["id"],
                title=values["title"],
                description=values["description"],
            )
        )

    required_statuses = {"clear", "review", "rework", "unknown"}
    raw_criteria = data.get("status_criteria")
    if not isinstance(raw_criteria, dict):
        raise ValueError("status_criteria must be an object")
    if any(not isinstance(value, str) or not value.strip() for value in raw_criteria.values()):
        raise ValueError("status_criteria values must be non-empty strings")
    status_criteria = dict(raw_criteria)
    if set(status_criteria) != required_statuses:
        raise ValueError(
            "status_criteria must contain exactly: clear, review, rework, unknown"
        )

    try:
        source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"Audit profile cannot be read: {path}") from exc

    return AuditProfile(
        name=profile_name,
        description=description,
        rules=tuple(parsed_rules),
        status_criteria=status_criteria,
        source=str(path),
        source_sha256=source_sha256,
    )
