import json

from mi_counsellor.counsellor import CrisisProtocolValidator, DraftResponse, Judge
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
