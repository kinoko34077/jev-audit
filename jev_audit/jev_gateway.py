from __future__ import annotations

import time
from typing import Any

from .models import AuditProfile, JevResult


LOCAL_NOULS = {
    "concrete_issue": (
        "このファイル群の内容そのものに、修正対象となる具体的な欠陥・矛盾・危険な挙動の証拠がありますか？ "
        "単に情報が無い、別ファイルを見ないと分からない、という理由だけではYesにしないでください。"
    ),
    "spec_mismatch": (
        "このファイル群の中で直接確認できる範囲に、仕様・説明・設定・実装の明確な食い違いがありますか？ "
        "比較対象が提示されていない場合は、推測だけでYesにしないでください。"
    ),
    "regression_risk": (
        "このファイル群の具体的な変更・実装から、既存挙動を壊しそうな要因を直接読み取れますか？ "
        "回帰テスト結果が見えないという理由だけではYesにしないでください。"
    ),
    "hidden_assumption": (
        "このファイル群に、未検証の前提へ明示的に依存している、または危険な仮定を置いている具体的な兆候がありますか？"
    ),
    "context_insufficient": (
        "このファイル群だけでは、局所的な問題の有無を判断するための文脈が不足していますか？ "
        "これはリスク判定とは別の情報量評価です。"
    ),
}


def _sdk():
    try:
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "typesafe-sdk is not installed. Run: python -m pip install typesafe-sdk"
        ) from exc
    return Choice, Noul, Score, TypeSafeClient


def _rule_criteria(profile: AuditProfile) -> dict[str, str]:
    criteria = {
        "none": "このファイル群から直接確認できる規定違反の兆候はない",
        "unknown": "文脈不足のため、どの規定が問題か判断できない",
    }
    for rule in profile.rules:
        criteria[rule.id] = f"{rule.title}: {rule.description}"
    return criteria


def _build_questions(profile: AuditProfile) -> dict[str, Any]:
    Choice, Noul, Score, _ = _sdk()

    questions: dict[str, Any] = {
        "local_status": Choice(
            instructions=(
                "このファイル群だけを高速簡易監査してください。欠落している外部証拠を違反扱いせず、"
                "ファイル内容から直接確認できる問題だけを重く評価してください。"
            ),
            criteria=profile.status_criteria,
        ),
        "dominant_issue_area": Choice(
            instructions=(
                "このファイル群に具体的な問題が見える場合、その主要領域を選んでください。"
                "明確な問題がなければnone、文脈不足だけならunknownを選んでください。"
            ),
            criteria=profile.issue_areas,
        ),
        "dominant_rule": Choice(
            instructions=(
                "このファイル群から直接確認できる監査規定上の問題がある場合、最も強く関係する規定を選んでください。"
                "規定違反の証拠がなければnone、判断不能ならunknownを選んでください。"
            ),
            criteria=_rule_criteria(profile),
        ),
        "severity": Score(
            instructions=(
                "このファイル群から直接確認できる具体的な問題の重大度を0〜4で評価してください。"
                "情報不足そのものは重大度に加算しないでください。"
            ),
            criteria=[
                "0: 具体的な問題は見当たらない",
                "1: 軽微。通常は修正不要または小修正",
                "2: 要確認。局所的な修正・レビュー候補",
                "3: 重要。修正または再検証が必要",
                "4: 重大。現状のまま扱うべきでない",
            ],
        ),
    }

    for key, prompt in LOCAL_NOULS.items():
        questions[key] = Noul(instructions=prompt)

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


def audit_with_jev(state: dict[str, Any], profile: AuditProfile) -> JevResult:
    _, _, _, TypeSafeClient = _sdk()
    questions = _build_questions(profile)

    started = time.perf_counter()
    with TypeSafeClient() as client:
        response = client.system_one(state=state, questions=questions)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _serialize_response(response, elapsed_ms)
