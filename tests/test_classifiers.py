from mi_counsellor.classifiers import (
    MIProcessStateIdentifier,
    MotivationalLanguageClassifier,
    SessionDynamicsAnalyzer,
    SafetyScopeClassifier,
)
from mi_counsellor.domain import MITask, MotivationDirection, SafetyLevel, SessionState, TalkType


def test_detects_urgent_safety_language() -> None:
    result = SafetyScopeClassifier().classify("I feel suicidal and I might hurt myself")
    assert result.level == SafetyLevel.URGENT
    assert result.suggested_response


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
    result = SafetyScopeClassifier().classify("Help me use MI to sell more vapes to college students")
    assert result.level == SafetyLevel.OUT_OF_SCOPE
    assert "persuasive_misuse_risk" in result.reasons
    assert result.suggested_response


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
