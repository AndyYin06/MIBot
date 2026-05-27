import mi_counsellor.cli as cli
from mi_counsellor.cli import format_miti_report
from mi_counsellor.domain import (
    MITIDimension,
    MITIDimensionRating,
    MITIFidelityReport,
    MITIMicroMetrics,
    SafetyAssessment,
    SafetyLevel,
)


class StubModel:
    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        return '{"level": "ok", "reasons": [], "suggested_response": ""}'


def test_build_safety_classifier_uses_classifier_model(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    model = StubModel()

    def fake_build_chat_model(env_prefix: str, default_model: str):
        calls.append((env_prefix, default_model))
        return model

    monkeypatch.setattr(cli, "build_chat_model", fake_build_chat_model)

    classifier = cli.build_safety_classifier()

    assert classifier.model is model
    assert calls == [("MI_CLASSIFIER_MODEL", "gpt-4o-mini")]


def test_format_miti_report_is_human_readable() -> None:
    report = MITIFidelityReport(
        overall_score=3.7,
        adherent=False,
        summary="Mostly empathic, with one directive moment.",
        dimension_ratings=(
            MITIDimensionRating(
                dimension=MITIDimension.EMPATHY,
                score=4,
                strengths=("Reflects the user's stress.",),
                concerns=(),
                evidence=("Smoking helps with stress.",),
            ),
            MITIDimensionRating(
                dimension=MITIDimension.AVOIDING_UNPERMITTED_ADVICE,
                score=2,
                strengths=(),
                concerns=("Gave advice without permission.",),
                evidence=("You should throw out your cigarettes.",),
            ),
        ),
        priority_recommendations=("Ask permission before offering strategies.",),
        micro_metrics=MITIMicroMetrics(
            reflection_count=2,
            question_count=3,
            reflection_to_question_ratio=0.67,
            complex_reflection_count=1,
            complex_reflection_percent=50.0,
            average_counsellor_words=22.5,
            advice_without_permission_count=1,
            drift_flag=True,
            concerns=("Question count exceeds reflection count; MI may feel interrogative.",),
        ),
    )

    text = format_miti_report(report)

    assert "MITI Fidelity Report" in text
    assert "Overall: 3.7/5.0 - Needs attention" in text
    assert "Empathy: 4/5" in text
    assert "Avoiding persuasion/advice without permission: 2/5" in text
    assert "Local validation metrics" in text
    assert "Reflections/questions: 2/3 (R:Q 0.67)" in text
    assert "Drift flag: yes" in text
    assert "{" not in text


def test_main_prints_streamed_response_chunks(monkeypatch, capsys) -> None:
    class FakeSafetyClassifier:
        def classify(self, text: str, transcript: str | None = None) -> SafetyAssessment:
            return SafetyAssessment(SafetyLevel.OK)

    class FakeEngine:
        last_stream_mode = "llm_stream"

        def opening_response(self, state):
            raise AssertionError("generated opening should be opt-in")

        def stream_next_response_with_deadline(self, state, *, first_token_timeout_seconds: float):
            assert first_token_timeout_seconds == 2.5
            yield "Chunked "
            yield "response."

        def local_validation(self, state, response):
            class Result:
                accepted = True
                problems = ()
                repair_instruction = ""

            return Result()

    class FakeCounsellor:
        def opening(self):
            return "Opening."

    class FakeMitiValidator:
        def evaluate(self, state):
            raise AssertionError("not used")

    inputs = iter(["Smoking helps me with stress.", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "build_safety_classifier", lambda: FakeSafetyClassifier())
    monkeypatch.setattr(cli, "build_engine", lambda: (FakeEngine(), FakeCounsellor()))
    monkeypatch.setattr(cli, "build_miti_validator", lambda: FakeMitiValidator())

    result = cli.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Counsellor: Opening." in output
    assert "Counsellor: Chunked response." in output


def test_main_uses_configured_first_token_timeout(monkeypatch, capsys) -> None:
    seen_timeouts: list[float] = []

    class FakeSafetyClassifier:
        def classify(self, text: str, transcript: str | None = None) -> SafetyAssessment:
            return SafetyAssessment(SafetyLevel.OK)

    class FakeEngine:
        last_stream_mode = "local_timeout"

        def stream_next_response_with_deadline(self, state, *, first_token_timeout_seconds: float):
            seen_timeouts.append(first_token_timeout_seconds)
            yield "Local reply."

        def local_validation(self, state, response):
            class Result:
                accepted = True
                problems = ()
                repair_instruction = ""

            return Result()

    class FakeCounsellor:
        def opening(self):
            return "Opening."

    inputs = iter(["Smoking helps me with stress.", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setenv("MI_FIRST_TOKEN_TIMEOUT_SECONDS", "0.25")
    monkeypatch.setattr(cli, "build_safety_classifier", lambda: FakeSafetyClassifier())
    monkeypatch.setattr(cli, "build_engine", lambda: (FakeEngine(), FakeCounsellor()))
    monkeypatch.setattr(cli, "build_miti_validator", lambda: object())

    result = cli.main()

    assert result == 0
    assert seen_timeouts == [0.25]
    assert "Counsellor: Local reply." in capsys.readouterr().out
