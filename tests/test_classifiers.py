from mi_counsellor.classifiers import (
    MIProcessStateIdentifier,
    MotivationalLanguageClassifier,
    SafetyScopeClassifier,
)
from mi_counsellor.domain import SafetyLevel, SessionState, TalkType


def test_detects_urgent_safety_language() -> None:
    result = SafetyScopeClassifier().classify("I feel suicidal and I might hurt myself")
    assert result.level == SafetyLevel.URGENT
    assert result.suggested_response


def test_detects_ambivalence() -> None:
    result = MotivationalLanguageClassifier().classify(
        "I want to quit because of my breathing, but smoking helps me with stress."
    )
    assert result.dominant == TalkType.AMBIVALENCE
    assert result.change_markers
    assert result.sustain_markers


def test_discord_sends_process_back_to_engaging() -> None:
    state = SessionState()
    state.add_turn("user", "I smoke.")
    state.add_turn("user", "You don't understand, this is pointless.")
    state.language = MotivationalLanguageClassifier().classify("You don't understand, this is pointless.")
    result = MIProcessStateIdentifier().identify(state)
    assert result.task.value == "engaging"
    assert result.slow_down is True
