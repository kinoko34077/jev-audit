from __future__ import annotations

import time
from typing import Any

from .models import AuditProfile, JevResult


FIXED_NOULS = {
    "needs_rework": "この対象には、完了扱いする前に修正すべき実質的な問題がありますか？",
    "needs_more_validation": "この対象は、完了扱いする前に追加の検証が必要ですか？",
    "evidence_insufficient": "現在提示されている証拠は、完了・妥当性を判断するには不足していますか？",
    "regression_risk": "既存機能・既存挙動を壊している可能性が無視できませんか？",
    "spec_mismatch": "要求・仕様・文書と実装または成果物の間に不整合がある可能性がありますか？",
    "hidden_assumption": "明示されていない前提や未確認の仮定に依存している可能性がありますか？",
}


def _sdk():
    try:
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "typesafe-sdk is not installed. Run: python -m pip install typesafe-sdk"
        ) from exc
    return Choice, Noul, Score, TypeSafeClient


def _build_questions(profile: AuditProfile, phase: str) -> dict[str, Any]:
    Choice, Noul, Score, _ = _sdk()
    scope = "プロジェクト全体" if phase == "final" else "このファイル群"

    questions: dict[str, Any] = {
        "overall_status": Choice(
            instructions=(
                f"{scope}を高速簡易監査してください。提示された規定と証拠だけを使い、"
                "最も適切な監査状態を選んでください。根拠が不足する場合は無理にOKへ寄せないでください。"
            ),
            criteria=profile.status_criteria,
        ),
        "dominant_issue_area": Choice(
            instructions=(
                f"{scope}に問題または不足がある場合、最も支配的な領域を選んでください。"
                "明確な問題が見当たらない場合は none を選んでください。"
            ),
            criteria=profile.issue_areas,
        ),
        "severity": Score(
            instructions=f"{scope}で見つかる問題・不足の重大度を0〜4で評価してください。",
            criteria=[
                "0: 明確な問題なし、または無視できる",
                "1: 軽微。完了判断には大きく影響しない",
                "2: 要確認。追加検証または小修正が望ましい",
                "3: 重要。完了前に修正または再検証が必要",
                "4: 重大。現状を完了扱いすべきでない",
            ],
        ),
    }

    for key, prompt in FIXED_NOULS.items():
        questions[key] = Noul(instructions=f"{scope}: {prompt}")

    for rule in profile.rules:
        questions[f"rule_violation__{rule.id}"] = Noul(
            instructions=(
                f"{scope}に、次の監査規定へ抵触している可能性のある具体的な証拠がありますか？ "
                f"[{rule.id}] {rule.title}: {rule.description}"
            )
        )

    return questions


def _serialize_response(response: Any, elapsed_ms: float) -> JevResult:
    choices: dict[str, dict[str, Any]] = {}
    for name, answer in response.choices.items():
        choices[name] = {
            "choice": answer.choice,
            "confidence": float(answer.confidence),
            "probabilities": {str(k): float(v) for k, v in answer.probabilities.items()},
        }

    nouls = {name: float(answer.noul) for name, answer in response.nouls.items()}

    scores: dict[str, dict[str, Any]] = {}
    for name, answer in response.scores.items():
        scores[name] = {
            "score": float(answer.score),
            "confidence": float(answer.confidence),
            "probabilities": {str(k): float(v) for k, v in answer.probabilities.items()},
            "legend": {str(k): v for k, v in answer.legend.items()},
        }

    usage = {
        "input_tokens": getattr(response.usage, "input_tokens", None),
        "output_tokens": getattr(response.usage, "output_tokens", None),
    }
    return JevResult(
        model=str(response.model),
        elapsed_ms=elapsed_ms,
        usage=usage,
        choices=choices,
        nouls=nouls,
        scores=scores,
    )


def audit_with_jev(state: dict[str, Any], profile: AuditProfile, phase: str) -> JevResult:
    _, _, _, TypeSafeClient = _sdk()
    questions = _build_questions(profile, phase)

    started = time.perf_counter()
    with TypeSafeClient() as client:
        response = client.system_one(state=state, questions=questions)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _serialize_response(response, elapsed_ms)
