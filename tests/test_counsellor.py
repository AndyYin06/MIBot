import json
import time
from typing import Any

import pytest

from mi_counsellor.counsellor import Counsellor, CrisisProtocolValidator, DraftResponse, FallbackPolicy, Judge, MIEngine
from mi_counsellor.domain import SafetyAssessment, SafetyLevel, SessionState


class AcceptingJudgeModel:
    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        return json.dumps(
            {
                "safe": True,
                "mi_consistent": True,
                "premature_advice": False,
                "premature_planning": False,
                "handles_scope": True,
                "concise": True,
                "ethical_context_ok": True,
                "problems": [],
                "repair_instruction": "",
            }
        )


class SequencedModel:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        self.messages.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class StreamingModel:
    def __init__(self, chunks: list[str], fallback_response: str | Exception | None = None) -> None:
        self.chunks = chunks
        self.fallback_response = fallback_response
        self.stream_messages: list[list[dict[str, str]]] = []
        self.messages: list[list[dict[str, str]]] = []

    def stream_complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4):
        self.stream_messages.append(messages)
        yield from self.chunks

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        self.messages.append(messages)
        if isinstance(self.fallback_response, Exception):
            raise self.fallback_response
        return self.fallback_response or counsellor_json("Fallback draft.")


class FailingStreamingModel(StreamingModel):
    def stream_complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4):
        self.stream_messages.append(messages)
        raise RuntimeError("stream unavailable")
        yield ""


class SlowStreamingModel(StreamingModel):
    def __init__(self, chunks: list[str], delay_seconds: float) -> None:
        super().__init__(chunks)
        self.delay_seconds = delay_seconds

    def stream_complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4):
        self.stream_messages.append(messages)
        time.sleep(self.delay_seconds)
        yield from self.chunks


def counsellor_json(response: str) -> str:
    return json.dumps(
        {
            "response": response,
            "intent": "open warmly",
            "mi_task_used": "engaging",
        }
    )


def judge_json(
    *,
    accepted: bool,
    repair_instruction: str = "",
    problems: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "safe": accepted,
            "mi_consistent": accepted,
            "premature_advice": False,
            "premature_planning": False,
            "handles_scope": accepted,
            "concise": True,
            "ethical_context_ok": True,
            "problems": problems or [],
            "repair_instruction": repair_instruction,
        }
    )


def build_engine(counsellor_model: Any, judge_model: Any) -> MIEngine:
    return MIEngine(Counsellor(counsellor_model), Judge(judge_model), FallbackPolicy())


def test_opening_is_natural_without_explicit_push_or_judge_language() -> None:
    opening = Counsellor(AcceptingJudgeModel()).opening()

    assert opening == (
        "Hi, I'm glad you're here. "
        "What would you like me to understand about smoking in your life right now?"
    )
    assert "push" not in opening.lower()
    assert "judg" not in opening.lower()


def test_opening_response_uses_first_turn_prompt_and_returns_accepted_model_response() -> None:
    counsellor_model = SequencedModel([counsellor_json("Hi, what's been on your mind about smoking lately?")])
    engine = build_engine(counsellor_model, AcceptingJudgeModel())

    opening = engine.opening_response(SessionState())

    assert opening == "Hi, what's been on your mind about smoking lately?"
    prompt = counsellor_model.messages[0][-1]["content"]
    assert "first counsellor turn" in prompt
    assert "before the user has said anything" in prompt
    assert "Return JSON only" in prompt


def test_opening_response_repairs_rejected_generated_opening_once() -> None:
    counsellor_model = SequencedModel(
        [
            counsellor_json("You should quit smoking today."),
            counsellor_json("Hi, what's been on your mind about smoking lately?"),
        ]
    )
    judge_model = SequencedModel(
        [
            judge_json(accepted=False, repair_instruction="Open without advice."),
            judge_json(accepted=True),
        ]
    )
    engine = build_engine(counsellor_model, judge_model)

    opening = engine.opening_response(SessionState())

    assert opening == "Hi, what's been on your mind about smoking lately?"
    assert len(counsellor_model.messages) == 2
    assert "Open without advice." in counsellor_model.messages[1][-1]["content"]


@pytest.mark.parametrize(
    ("counsellor_responses", "judge_responses"),
    [
        ([RuntimeError("model down")], [judge_json(accepted=True)]),
        (["not json"], [judge_json(accepted=True)]),
        ([counsellor_json("")], [judge_json(accepted=True)]),
        (
            [
                counsellor_json("Hi, what's been on your mind about smoking lately?"),
                counsellor_json("Hi, what feels important about smoking lately?"),
            ],
            [
                judge_json(accepted=False, repair_instruction="Try again."),
                judge_json(accepted=False, problems=["still not right"]),
            ],
        ),
    ],
)
def test_opening_response_falls_back_when_generation_or_validation_fails(
    counsellor_responses: list[str | Exception],
    judge_responses: list[str],
) -> None:
    engine = build_engine(SequencedModel(counsellor_responses), SequencedModel(judge_responses))

    opening = engine.opening_response(SessionState())

    assert opening == Counsellor(AcceptingJudgeModel()).opening()


def test_opening_response_falls_back_when_generated_opening_uses_explicit_push_or_judge_language() -> None:
    counsellor_model = SequencedModel(
        [
            counsellor_json("Hi, I will not push or judge you about smoking."),
            counsellor_json("Hi, I will not push or judge you about smoking."),
        ]
    )
    engine = build_engine(counsellor_model, AcceptingJudgeModel())

    opening = engine.opening_response(SessionState())

    assert opening == Counsellor(AcceptingJudgeModel()).opening()
    assert "push" not in opening.lower()
    assert "judg" not in opening.lower()


def test_counsellor_prompt_includes_general_behavior_guidance() -> None:
    model = SequencedModel([counsellor_json("This conversation may not feel useful right now.")])
    state = SessionState()
    state.add_turn("user", "This is pointless.")

    Counsellor(model).draft(state)

    prompt = model.messages[0][-1]["content"]
    assert "latest user turn" in prompt
    assert "frustration, boredom, refusal, or disengagement" in prompt
    assert "Do not pivot back to change talk unless" in prompt
    assert "tryna leave" not in prompt


def test_counsellor_prompt_treats_smoking_related_health_feedback_as_in_scope() -> None:
    model = SequencedModel([counsellor_json("That sounds like a lot to take in.")])
    state = SessionState()
    state.add_turn("user", "The doctor said my lungs are getting worse and to see someone about it.")

    Counsellor(model).draft(state)

    prompt = model.messages[0][-1]["content"]
    assert "clinician" in prompt
    assert "feedback related to smoking" in prompt
    assert "treat it as in-scope MI material" in prompt
    assert "avoid diagnosis or medical instructions" in prompt


def test_stream_next_response_yields_counsellor_chunks_without_judge_call() -> None:
    counsellor_model = StreamingModel(["That sounds ", "stressful."])
    judge_model = SequencedModel([RuntimeError("judge should not block streaming")])
    engine = build_engine(counsellor_model, judge_model)
    state = SessionState()
    state.add_turn("user", "Smoking helps me with stress.")

    chunks = list(engine.stream_next_response(state))

    assert chunks == ["That sounds ", "stressful."]
    assert len(counsellor_model.stream_messages) == 1
    assert "Return only the counsellor message text." in counsellor_model.stream_messages[0][-1]["content"]
    assert judge_model.messages == []


def test_stream_next_response_with_deadline_uses_local_reply_when_streaming_unavailable() -> None:
    counsellor_model = FailingStreamingModel([], RuntimeError("draft should not be called"))
    engine = build_engine(counsellor_model, AcceptingJudgeModel())
    state = SessionState()
    state.add_turn("user", "Smoking helps me with stress.")

    chunks = list(engine.stream_next_response_with_deadline(state, first_token_timeout_seconds=0.1))

    assert chunks == [Counsellor(counsellor_model).local_response(state)]
    assert engine.last_stream_mode == "local_stream_error"
    assert len(counsellor_model.stream_messages) == 1
    assert counsellor_model.messages == []


def test_stream_next_response_with_deadline_uses_local_reply_when_first_chunk_is_slow() -> None:
    counsellor_model = SlowStreamingModel(["Late LLM reply."], delay_seconds=0.05)
    engine = build_engine(counsellor_model, AcceptingJudgeModel())
    state = SessionState()
    state.add_turn("user", "Smoking helps me with stress.")

    started = time.perf_counter()
    chunks = list(engine.stream_next_response_with_deadline(state, first_token_timeout_seconds=0.01))

    assert chunks == [Counsellor(counsellor_model).local_response(state)]
    assert time.perf_counter() - started < 0.04
    assert engine.last_stream_mode == "local_timeout"


def test_stream_next_response_with_deadline_streams_prompt_first_chunk() -> None:
    counsellor_model = StreamingModel(["That sounds ", "stressful."])
    judge_model = SequencedModel([RuntimeError("judge should not block streaming")])
    engine = build_engine(counsellor_model, judge_model)
    state = SessionState()
    state.add_turn("user", "Smoking helps me with stress.")

    chunks = list(engine.stream_next_response_with_deadline(state, first_token_timeout_seconds=0.1))

    assert chunks == ["That sounds ", "stressful."]
    assert engine.last_stream_mode == "llm_stream"
    assert judge_model.messages == []


def test_stream_next_response_routes_urgent_turn_to_fallback_without_generation() -> None:
    counsellor_model = StreamingModel(["unused"])
    engine = build_engine(counsellor_model, AcceptingJudgeModel())
    state = SessionState()
    state.safety = SafetyAssessment(SafetyLevel.URGENT, ("urgent_risk",), "Use crisis support now.")

    chunks = list(engine.stream_next_response_with_deadline(state, first_token_timeout_seconds=0.1))

    assert chunks == ["Use crisis support now."]
    assert engine.last_stream_mode == "safety_fallback"
    assert counsellor_model.stream_messages == []


def test_judge_prompt_includes_guidance_to_prioritize_latest_user_turn() -> None:
    model = SequencedModel([judge_json(accepted=True)])
    state = SessionState()
    state.add_turn("user", "This is pointless.")

    Judge(model).evaluate(state, DraftResponse("What matters most about smoking?", "ask", "evoking"))

    prompt = model.messages[0][-1]["content"]
    assert "Response guidance" in prompt
    assert "latest user turn" in prompt
    assert "responds to a state label instead of the user's" in model.messages[0][0]["content"]


def test_judge_prompt_rejects_treating_smoking_related_health_feedback_as_out_of_scope() -> None:
    model = SequencedModel([judge_json(accepted=True)])
    state = SessionState()
    state.add_turn("user", "The doctor said my lungs are getting worse and to see someone about it.")

    Judge(model).evaluate(state, DraftResponse("That is out of scope for me.", "defer", "engaging"))

    assert "smoking-related health concerns or clinician" in model.messages[0][0]["content"]
    assert "clinician" in model.messages[0][-1]["content"]
    assert "feedback related to smoking" in model.messages[0][-1]["content"]


def test_non_safety_fallback_uses_general_repair_instead_of_stock_mi_scripts() -> None:
    response = FallbackPolicy().response(SessionState())

    assert response == (
        "I may be missing what matters most in this moment. "
        "What would you prefer to do from here?"
    )
    assert "mixed pieces" not in response
    assert "smoking protects" not in response


def test_crisis_protocol_validator_requires_specific_safety_behaviors() -> None:
    weak = "I am sorry this is hard. Tell me more about what is going on."
    strong = (
        "Thank you for telling me. Your safety matters more than quitting smoking right now. "
        "If you might hurt yourself, call emergency services now, or call/text 988 for crisis support. "
        "Is there someone nearby you can be with while you get support?"
    )

    validator = CrisisProtocolValidator()

    assert "specific_resources" in validator.missing_behaviors(weak)
    assert validator.passes(strong)


def test_judge_adds_local_advice_permission_problem() -> None:
    state = SessionState()
    state.add_turn("user", "I am not ready to quit.")
    draft = DraftResponse("You should throw out your cigarettes tonight.", "advise", "planning")

    result = Judge(AcceptingJudgeModel()).evaluate(state, draft)

    assert result.accepted is False
    assert result.premature_advice is True
    assert any("permission" in problem for problem in result.problems)


def test_judge_rejects_incomplete_crisis_response_even_if_model_accepts() -> None:
    state = SessionState()
    state.safety = SafetyAssessment(SafetyLevel.URGENT, ("urgent_risk",))
    state.add_turn("user", "I feel suicidal.")
    draft = DraftResponse("I am sorry. What feels hardest right now?", "empathize", "engaging")

    result = Judge(AcceptingJudgeModel()).evaluate(state, draft)

    assert result.accepted is False
    assert result.safe is False
    assert any("crisis protocol missing" in problem for problem in result.problems)
