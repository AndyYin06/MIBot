import json

from mi_counsellor.domain import MITIDimension, SessionState
from mi_counsellor.miti import MITIFidelityValidator, MITIMicroMetricAnalyzer, parse_miti_report


class FakeMITIModel:
    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        assert "MITI-informed global coding lens" in messages[0]["content"]
        assert "counsellor:" in messages[1]["content"]
        return json.dumps(
            {
                "overall_score": 3.5,
                "adherent": False,
                "summary": "Mostly empathic, but advice was offered too quickly.",
                "dimension_ratings": [
                    {
                        "dimension": "cultivating_change_talk",
                        "score": 3,
                        "strengths": ["Asked one open question."],
                        "concerns": ["Did not evoke enough user reasons."],
                        "evidence": ["What matters to you?"],
                    },
                    {
                        "dimension": "avoiding_unpermitted_advice",
                        "score": 2,
                        "strengths": [],
                        "concerns": ["Gave a quit plan without permission."],
                        "evidence": ["You should throw out your cigarettes."],
                    },
                ],
                "priority_recommendations": ["Ask permission before advice."],
            }
        )


def test_miti_validator_returns_structured_report() -> None:
    state = SessionState()
    state.add_turn("counsellor", "What feels important about smoking right now?")
    state.add_turn("user", "I want to quit, but it helps with stress.")
    state.add_turn("counsellor", "You should throw out your cigarettes.")

    report = MITIFidelityValidator(FakeMITIModel()).evaluate(state)

    assert report.overall_score == 3.5
    assert report.adherent is False
    assert report.micro_metrics
    assert report.micro_metrics.advice_without_permission_count == 1
    assert report.dimension_ratings[0].dimension == MITIDimension.CULTIVATING_CHANGE_TALK
    assert len(report.dimension_ratings) == 6
    assert report.priority_recommendations == ("Ask permission before advice.",)


def test_parse_miti_report_clamps_scores() -> None:
    report = parse_miti_report(
        {
            "overall_score": 7,
            "dimension_ratings": [
                {
                    "dimension": "empathy",
                    "score": 9,
                    "strengths": ["Warm reflection."],
                }
            ],
        }
    )

    assert report.overall_score == 5.0
    empathy_rating = next(rating for rating in report.dimension_ratings if rating.dimension == MITIDimension.EMPATHY)
    assert empathy_rating.score == 5


def test_micro_metrics_track_miti_behavior_counts_and_drift() -> None:
    state = SessionState()
    state.add_turn("counsellor", "It sounds like smoking helps you get through stress. What matters most today?")
    state.add_turn("user", "It helps, but I hate the coughing.")
    state.add_turn(
        "counsellor",
        "Part of you values the relief, while another part notices the cost. "
        "You should throw out your cigarettes tonight.",
    )
    state.add_turn("user", "That feels pushy.")
    state.add_turn(
        "counsellor",
        "Why not quit? What stops you? What would make you change? What if you tried harder?",
    )

    metrics = MITIMicroMetricAnalyzer().analyze(state)

    assert metrics.reflection_count == 2
    assert metrics.question_count == 5
    assert metrics.complex_reflection_count == 1
    assert metrics.advice_without_permission_count == 1
    assert metrics.drift_flag is True
    assert metrics.concerns
