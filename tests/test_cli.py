from mi_counsellor.cli import format_miti_report
from mi_counsellor.domain import MITIDimension, MITIDimensionRating, MITIFidelityReport


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
    )

    text = format_miti_report(report)

    assert "MITI Fidelity Report" in text
    assert "Overall: 3.7/5.0 - Needs attention" in text
    assert "Empathy: 4/5" in text
    assert "Avoiding persuasion/advice without permission: 2/5" in text
    assert "{" not in text
