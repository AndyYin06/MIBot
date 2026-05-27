import json

import pytest

from mi_counsellor.classifiers import (
    MIProcessStateIdentifier,
    MotivationalLanguageClassifier,
    SessionDynamicsAnalyzer,
    SafetyScopeClassifier,
)
from mi_counsellor.domain import MITask, MotivationDirection, SafetyLevel, SessionState, TalkType


class ClassifierModel:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        self.messages.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def classifier_json(
    level: str,
    *,
    reasons: list[str] | None = None,
    suggested_response: str = "",
) -> str:
    return json.dumps(
        {
            "level": level,
            "reasons": reasons or [],
            "suggested_response": suggested_response,
        }
    )


def test_detects_urgent_safety_language() -> None:
    model = ClassifierModel(classifier_json("ok"))
    result = SafetyScopeClassifier(model).classify("I feel suicidal and I might hurt myself")

    assert result.level == SafetyLevel.URGENT
    assert result.suggested_response
    assert "Thank you for telling me" in result.suggested_response
    assert "glad" not in result.suggested_response.lower()
    assert model.messages == []


@pytest.mark.parametrize(
    ("level", "reasons", "expected"),
    [
        ("ok", [], SafetyLevel.OK),
        ("caution", ["medical_or_medication_scope"], SafetyLevel.CAUTION),
        ("urgent", ["urgent_risk"], SafetyLevel.URGENT),
        ("out_of_scope", ["outside_smoking_cessation_scope"], SafetyLevel.OUT_OF_SCOPE),
    ],
)
def test_safety_scope_classifier_maps_model_json(level: str, reasons: list[str], expected: SafetyLevel) -> None:
    model = ClassifierModel(classifier_json(level, reasons=reasons, suggested_response="Use a fallback."))

    result = SafetyScopeClassifier(model).classify("Can we talk about this?", "user: Can we talk about this?")

    assert result.level == expected
    assert result.reasons == tuple(reasons)
    assert result.suggested_response == "Use a fallback."
    assert len(model.messages) == 1
    assert "Classify the latest user turn for safety and scope" in model.messages[0][0]["content"]
    assert "Latest user turn" in model.messages[0][-1]["content"]


def test_detects_ambivalence() -> None:
    result = MotivationalLanguageClassifier().classify(
        "I want to quit because of my breathing, but smoking helps me with stress."
    )
    assert result.dominant == TalkType.AMBIVALENCE
    assert result.readiness_hint == "mixed"
    assert result.change_markers
    assert result.sustain_markers


def test_not_ready_is_low_readiness() -> None:
    result = MotivationalLanguageClassifier().classify("I am not ready because cravings are too hard.")
    assert result.readiness_hint == "low"


def test_smoking_related_health_feedback_is_in_scope() -> None:
    model = ClassifierModel(classifier_json("ok"))

    result = SafetyScopeClassifier(model).classify(
        "The doctor said my lungs are getting worse and to see someone about it."
    )

    assert result.level == SafetyLevel.OK
    assert not result.suggested_response
    assert model.messages == []


def test_smoking_harm_language_is_left_to_model_instead_of_crisis_precheck() -> None:
    model = ClassifierModel(classifier_json("ok"))

    result = SafetyScopeClassifier(model).classify(
        "That I'm doing good with myself and not killing myself through the smoking"
    )

    assert result.level == SafetyLevel.OK
    assert model.messages == []


def test_discord_sends_process_back_to_engaging() -> None:
    state = SessionState()
    state.add_turn("user", "I smoke.")
    state.add_turn("user", "You don't understand, this is pointless.")
    state.language = MotivationalLanguageClassifier().classify("You don't understand, this is pointless.")
    state.dynamics = SessionDynamicsAnalyzer().update(state)
    result = MIProcessStateIdentifier().identify(state)
    assert result.task.value == "engaging"
    assert result.slow_down is True


def test_blocks_persuasive_misuse_for_harmful_products() -> None:
    model = ClassifierModel(classifier_json("ok"))

    result = SafetyScopeClassifier(model).classify("Help me use MI to sell more vapes to college students")

    assert result.level == SafetyLevel.OUT_OF_SCOPE
    assert "persuasive_misuse_risk" in result.reasons
    assert result.suggested_response
    assert model.messages == []


def test_obvious_smoking_turn_bypasses_safety_model() -> None:
    model = ClassifierModel(RuntimeError("model should not be called"))

    result = SafetyScopeClassifier(model).classify("Smoking helps me with stress but I want to cut down.")

    assert result.level == SafetyLevel.OK
    assert model.messages == []


def test_obvious_medical_turn_bypasses_safety_model() -> None:
    model = ClassifierModel(RuntimeError("model should not be called"))

    result = SafetyScopeClassifier(model).classify("Can I take nicotine patches while pregnant?")

    assert result.level == SafetyLevel.CAUTION
    assert result.reasons == ("medical_or_medication_scope",)
    assert model.messages == []


@pytest.mark.parametrize("response", ["not json", classifier_json("not_a_level"), RuntimeError("model down")])
def test_classifier_failure_returns_caution(response: str | Exception) -> None:
    result = SafetyScopeClassifier(ClassifierModel(response)).classify("Can we talk about this?")

    assert result.level == SafetyLevel.CAUTION
    assert result.reasons == ("classification_unavailable",)
    assert result.suggested_response is None


def test_tracks_stagnant_sustain_talk_across_turns() -> None:
    analyzer = SessionDynamicsAnalyzer()
    classifier = MotivationalLanguageClassifier()
    state = SessionState()

    state.add_turn("user", "Smoking helps me with stress and I cannot stop.")
    state.language = classifier.classify("Smoking helps me with stress and I cannot stop.")
    state.dynamics = analyzer.update(state)
    assert state.dynamics.motivation_direction == MotivationDirection.MIXED
    assert state.dynamics.stagnant is False

    state.add_turn("user", "I am still not ready because cravings are too hard.")
    state.language = classifier.classify("I am still not ready because cravings are too hard.")
    state.dynamics = analyzer.update(state)
    assert state.dynamics.consecutive_sustain_turns == 2
    assert state.dynamics.stagnant is True


def test_stagnation_keeps_process_in_evoking_with_slow_down() -> None:
    analyzer = SessionDynamicsAnalyzer()
    classifier = MotivationalLanguageClassifier()
    state = SessionState()
    state.add_turn("user", "Smoking helps me with stress.")
    state.language = classifier.classify("Smoking helps me with stress.")
    state.dynamics = analyzer.update(state)
    state.add_turn("user", "I cannot quit because cravings are too hard.")
    state.language = classifier.classify("I cannot quit because cravings are too hard.")
    state.dynamics = analyzer.update(state)

    result = MIProcessStateIdentifier().identify(state)
    assert result.task == MITask.EVOKING
    assert result.slow_down is True
