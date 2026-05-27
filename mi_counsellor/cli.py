from __future__ import annotations

import copy
import os
import sys
import threading
import time

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


def build_safety_classifier() -> SafetyScopeClassifier:
    model = build_chat_model("MI_CLASSIFIER_MODEL", "gpt-4o-mini")
    return SafetyScopeClassifier(model)


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

    if report.micro_metrics:
        metrics = report.micro_metrics
        ratio = "n/a" if metrics.reflection_to_question_ratio is None else f"{metrics.reflection_to_question_ratio:.2f}"
        lines.append("")
        lines.append("Local validation metrics")
        lines.append(f"- Reflections/questions: {metrics.reflection_count}/{metrics.question_count} (R:Q {ratio})")
        lines.append(
            f"- Complex reflections: {metrics.complex_reflection_count} ({metrics.complex_reflection_percent:.1f}%)"
        )
        lines.append(f"- Average counsellor turn length: {metrics.average_counsellor_words:.1f} words")
        lines.append(f"- Advice without nearby permission: {metrics.advice_without_permission_count}")
        lines.append(f"- Drift flag: {'yes' if metrics.drift_flag else 'no'}")
        if metrics.concerns:
            lines.append(f"  Concerns: {'; '.join(metrics.concerns)}")

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


def _latency_debug_enabled() -> bool:
    return os.getenv("MI_LATENCY_DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _first_token_timeout_seconds() -> float:
    raw = os.getenv("MI_FIRST_TOKEN_TIMEOUT_SECONDS", "2.5")
    try:
        timeout = float(raw)
    except ValueError:
        return 2.5
    return max(0.0, timeout)


def _generated_opening_enabled() -> bool:
    return os.getenv("MI_GENERATED_OPENING", "").lower() in {"1", "true", "yes", "on"}


def _print_latency(timings: dict[str, float], *, mode: str) -> None:
    if not _latency_debug_enabled():
        return
    parts = [f"{name}={value * 1000:.0f}ms" for name, value in timings.items()]
    print(f"[latency] mode={mode} {' '.join(parts)}", file=sys.stderr)


def _run_diagnostic_judge(engine: MIEngine, state: SessionState, response: str) -> None:
    started = time.perf_counter()
    try:
        result = engine.diagnostic_judge(state, response)
    except Exception as exc:
        print(f"[diagnostic] judge failed after {(time.perf_counter() - started) * 1000:.0f}ms: {exc}", file=sys.stderr)
        return
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not result.accepted:
        print(
            f"[diagnostic] judge rejected streamed response after {elapsed_ms:.0f}ms: "
            f"{'; '.join(result.problems) or result.repair_instruction}",
            file=sys.stderr,
        )
    else:
        print(f"[diagnostic] judge accepted streamed response after {elapsed_ms:.0f}ms", file=sys.stderr)


def main() -> int:
    safety_classifier = build_safety_classifier()
    language_classifier = MotivationalLanguageClassifier()
    dynamics_analyzer = SessionDynamicsAnalyzer()
    process_identifier = MIProcessStateIdentifier()
    engine, counsellor = build_engine()
    miti_validator = build_miti_validator()
    state = SessionState()

    opening = engine.opening_response(state) if _generated_opening_enabled() else counsellor.opening()
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
        turn_started = time.perf_counter()
        safety_started = time.perf_counter()
        state.safety = safety_classifier.classify(user_text, state.transcript())
        timings = {"safety": time.perf_counter() - safety_started}
        state.language = language_classifier.classify(user_text)
        state.dynamics = dynamics_analyzer.update(state)
        state.process = process_identifier.identify(state)

        try:
            print("\nCounsellor: ", end="", flush=True)
            response_parts: list[str] = []
            stream_started = time.perf_counter()
            first_chunk_at: float | None = None
            for chunk in engine.stream_next_response_with_deadline(
                state,
                first_token_timeout_seconds=_first_token_timeout_seconds(),
            ):
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                    timings["first_token"] = first_chunk_at - stream_started
                response_parts.append(chunk)
                print(chunk, end="", flush=True)
            print()
            response = "".join(response_parts).strip()
            timings["stream_complete"] = time.perf_counter() - stream_started
        except Exception as exc:
            response = FallbackPolicy().response(state)
            print(f"[diagnostic] model path failed, used fallback: {exc}", file=sys.stderr)
            print(f"\nCounsellor: {response}")

        validation_started = time.perf_counter()
        local_result = engine.local_validation(state, response)
        timings["local_validation"] = time.perf_counter() - validation_started
        timings["turn_total"] = time.perf_counter() - turn_started
        if _latency_debug_enabled() and not local_result.accepted:
            print(
                f"[diagnostic] local validation flagged streamed response: "
                f"{'; '.join(local_result.problems) or local_result.repair_instruction}",
                file=sys.stderr,
            )
        if _latency_debug_enabled() and response:
            diagnostic_state = copy.deepcopy(state)
            thread = threading.Thread(
                target=_run_diagnostic_judge,
                args=(engine, diagnostic_state, response),
                daemon=True,
            )
            thread.start()
        _print_latency(timings, mode=engine.last_stream_mode)
        state.add_turn("counsellor", response)


if __name__ == "__main__":
    raise SystemExit(main())
