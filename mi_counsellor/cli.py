from __future__ import annotations

import sys

from mi_counsellor.classifiers import (
    MIProcessStateIdentifier,
    MotivationalLanguageClassifier,
    SessionDynamicsAnalyzer,
    SafetyScopeClassifier,
)
from mi_counsellor.counsellor import Counsellor, FallbackPolicy, Judge, MIEngine
from mi_counsellor.domain import MITIFidelityReport, SessionState
from mi_counsellor.llm import build_chat_model
from mi_counsellor.miti import MITIFidelityValidator


def build_engine() -> tuple[MIEngine, Counsellor]:
    counsellor_model = build_chat_model("MI_COUNSELLOR_MODEL", "gpt-4o-mini")
    judge_model = build_chat_model("MI_JUDGE_MODEL", "gpt-4o-mini")
    counsellor = Counsellor(counsellor_model)
    return MIEngine(counsellor, Judge(judge_model), FallbackPolicy()), counsellor


def build_miti_validator() -> MITIFidelityValidator:
    model = build_chat_model("MI_MITI_MODEL", "gpt-4o-mini")
    return MITIFidelityValidator(model)


def print_state(state: SessionState) -> None:
    import json

    data = {
        "safety": {
            "level": state.safety.level.value,
            "reasons": state.safety.reasons,
        },
        "mi_process": {
            "task": state.process.task.value,
            "confidence": state.process.confidence,
            "rationale": state.process.rationale,
            "slow_down": state.process.slow_down,
        },
        "motivational_language": {
            "dominant": state.language.dominant.value,
            "change_markers": state.language.change_markers,
            "sustain_markers": state.language.sustain_markers,
            "discord_markers": state.language.discord_markers,
            "readiness_hint": state.language.readiness_hint,
            "confidence": state.language.confidence,
        },
        "session_dynamics": {
            "rapport": state.dynamics.rapport,
            "goal_alignment": state.dynamics.goal_alignment,
            "motivation_direction": state.dynamics.motivation_direction.value,
            "consecutive_sustain_turns": state.dynamics.consecutive_sustain_turns,
            "consecutive_discord_turns": state.dynamics.consecutive_discord_turns,
            "stagnant": state.dynamics.stagnant,
            "recommended_strategy": state.dynamics.recommended_strategy,
        },
    }
    print(json.dumps(data, indent=2))


def print_miti_report(report: MITIFidelityReport) -> None:
    print(format_miti_report(report))


def format_miti_report(report: MITIFidelityReport) -> str:
    adherence = "Adherent" if report.adherent else "Needs attention"
    lines = [
        "MITI Fidelity Report",
        f"Overall: {report.overall_score:.1f}/5.0 - {adherence}",
    ]
    if report.summary:
        lines.extend(("", report.summary))

    lines.append("")
    lines.append("Dimension scores")
    for rating in report.dimension_ratings:
        lines.append(f"- {_label_dimension(rating.dimension.value)}: {rating.score}/5")
        if rating.strengths:
            lines.append(f"  Strengths: {'; '.join(rating.strengths)}")
        if rating.concerns:
            lines.append(f"  Concerns: {'; '.join(rating.concerns)}")
        if rating.evidence:
            lines.append(f"  Evidence: {'; '.join(rating.evidence)}")

    if report.priority_recommendations:
        lines.append("")
        lines.append("Priority recommendations")
        for recommendation in report.priority_recommendations:
            lines.append(f"- {recommendation}")

    return "\n".join(lines)


def _label_dimension(value: str) -> str:
    labels = {
        "cultivating_change_talk": "Cultivating change talk",
        "softening_sustain_talk": "Softening sustain talk",
        "partnership": "Partnership",
        "empathy": "Empathy",
        "autonomy_support": "Autonomy support",
        "avoiding_unpermitted_advice": "Avoiding persuasion/advice without permission",
    }
    return labels.get(value, value.replace("_", " ").capitalize())


def main() -> int:
    safety_classifier = SafetyScopeClassifier()
    language_classifier = MotivationalLanguageClassifier()
    dynamics_analyzer = SessionDynamicsAnalyzer()
    process_identifier = MIProcessStateIdentifier()
    engine, counsellor = build_engine()
    miti_validator = build_miti_validator()
    state = SessionState()

    opening = counsellor.opening()
    state.add_turn("counsellor", opening)
    print(f"Counsellor: {opening}")

    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCounsellor: Thanks for talking with me. Take care of yourself.")
            return 0

        if not user_text:
            continue
        if user_text.lower() in {"/quit", "quit", "exit", "/exit"}:
            print("Counsellor: Thanks for talking with me. Take care of yourself.")
            return 0
        if user_text.lower() == "/state":
            print_state(state)
            continue
        if user_text.lower() == "/miti":
            try:
                print_miti_report(miti_validator.evaluate(state))
            except Exception as exc:
                print(f"[diagnostic] MITI validation failed: {exc}", file=sys.stderr)
            continue

        state.add_turn("user", user_text)
        state.safety = safety_classifier.classify(user_text)
        state.language = language_classifier.classify(user_text)
        state.dynamics = dynamics_analyzer.update(state)
        state.process = process_identifier.identify(state)

        try:
            response = engine.next_response(state)
        except Exception as exc:
            response = FallbackPolicy().response(state)
            print(f"[diagnostic] model path failed, used fallback: {exc}", file=sys.stderr)

        state.add_turn("counsellor", response)
        print(f"\nCounsellor: {response}")


if __name__ == "__main__":
    raise SystemExit(main())
