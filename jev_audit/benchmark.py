from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .jev_gateway import audit_with_jev
from .models import AuditProfile, AuditRule, JevResult


@dataclass(frozen=True)
class BenchmarkFixture:
    id: str
    content: str
    change: str
    expectation: str


@dataclass(frozen=True)
class BenchmarkObservation:
    fixture_id: str
    score: int | None
    error: str | None


BENCHMARK_PROFILE = AuditProfile(
    name="benchmark-v1",
    description="Fixed synthetic benchmark contract; independent of caller profiles.",
    status_criteria={
        "clear": "No concrete actionable issue is supported by the supplied fixture.",
        "review": "A concrete concern is supported and should be reviewed.",
        "rework": "A concrete defect strongly supports corrective work.",
        "unknown": "The supplied fixture is intentionally insufficient for a supported conclusion.",
    },
    rules=(
        AuditRule("BENCH-CORRECT", "Correctness", "Identify concrete defects supported by the fixture."),
        AuditRule("BENCH-SPEC", "Specification consistency", "Identify direct specification or behavior contradictions."),
        AuditRule("BENCH-REGRESSION", "Regression risk", "Identify direct change-related regression hazards."),
        AuditRule("BENCH-UNCERTAINTY", "Uncertainty", "Preserve unknown when evidence is intentionally insufficient."),
    ),
    source="builtin:benchmark-v1",
    source_sha256="benchmark-v1",
)

FIXTURES = (
    BenchmarkFixture("clear-code", "def add(a, b):\n    return a + b\n", "", "clear"),
    BenchmarkFixture("concrete-issue", "def divide(a, b):\n    return a / b\n", "Callers may pass b=0.", "concrete_issue"),
    BenchmarkFixture("spec-mismatch", "# spec: return lowercase\ndef normalize(s):\n    return s.upper()\n", "", "spec_mismatch"),
    BenchmarkFixture("regression-risk", "def parse(value):\n    return int(value)\n", "Previously invalid values returned None; now they raise.", "regression_risk"),
    BenchmarkFixture("insufficient-context", "def adapter(value):\n    return external(value)\n", "No contract for external() is provided.", "unknown"),
    BenchmarkFixture("strong-rework", "def authorized(user):\n    return True\n", "Authorization guard was replaced with unconditional True.", "rework"),
    BenchmarkFixture("benign-config-docs", "# timeout is documented as 30s\nTIMEOUT_SECONDS = 30\n", "", "clear"),
    BenchmarkFixture("mild-review", "def cache_key(user_id, locale):\n    return str(user_id)\n", "Locale was added to callers but is not yet part of the cache key.", "review"),
)


def fixture_ids() -> tuple[str, ...]:
    return tuple(item.id for item in FIXTURES)


def _probabilities(result: JevResult) -> dict[str, float]:
    return result.choices.get("local_status", {}).get("probabilities", {})


def score_fixture(fixture: BenchmarkFixture, result: JevResult) -> int:
    choice = str(result.choices.get("local_status", {}).get("choice") or "")
    probabilities = _probabilities(result)
    expectation = fixture.expectation
    matched = False
    if expectation == "clear":
        matched = choice == "clear"
    elif expectation == "concrete_issue":
        matched = float(result.nouls.get("concrete_issue", 0.0)) >= 0.65
    elif expectation == "spec_mismatch":
        matched = float(result.nouls.get("spec_mismatch", 0.0)) >= 0.65
    elif expectation == "regression_risk":
        matched = float(result.nouls.get("regression_risk", 0.0)) >= 0.65
    elif expectation == "unknown":
        matched = choice == "unknown" or float(probabilities.get("unknown", 0.0)) >= 0.60
    elif expectation == "rework":
        matched = choice == "rework" or (
            float(result.nouls.get("concrete_issue", 0.0)) >= 0.80
            and float(probabilities.get("rework", 0.0)) >= 0.60
        )
    elif expectation == "review":
        actionable = float(probabilities.get("review", 0.0)) + float(probabilities.get("rework", 0.0))
        matched = choice == "review" or actionable >= 0.60
    return 100 if matched else 0


def _fixture_state(fixture: BenchmarkFixture) -> dict:
    entry = {
        "path": f"benchmark/{fixture.id}.py",
        "truncated": False,
        "content": fixture.content,
    }
    if fixture.change:
        entry["change"] = fixture.change
    return {"files": [entry]}


def run_benchmark(
    fixture_index: int,
    model: str,
    *,
    audit_func: Callable = audit_with_jev,
) -> BenchmarkObservation:
    fixture = FIXTURES[fixture_index % len(FIXTURES)]
    try:
        result = audit_func(
            _fixture_state(fixture),
            BENCHMARK_PROFILE,
            model=model,
            timeout=45.0,
        )
        return BenchmarkObservation(
            fixture_id=fixture.id,
            score=score_fixture(fixture, result),
            error=None,
        )
    except Exception:
        return BenchmarkObservation(
            fixture_id=fixture.id,
            score=None,
            error="provider_error",
        )
