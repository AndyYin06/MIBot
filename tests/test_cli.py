from mi_counsellor.cli import format_miti_report
from mi_counsellor.domain import MITIDimension, MITIDimensionRating, MITIFidelityReport, MITIMicroMetrics


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
