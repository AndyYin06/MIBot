from __future__ import annotations

from mi_counsellor.domain import (
    MITIDimension,
    MITIDimensionRating,
    MITIFidelityReport,
    ConversationTurn,
    SessionState,
)
from mi_counsellor.llm import ChatModel, parse_json_object
from mi_counsellor.prompts import MI_STYLE_GUIDE, MITI_FIDELITY_JSON_PROMPT


class MITIFidelityValidator:
    """Transcript-level MITI-informed evaluator for counsellor fidelity."""

    def __init__(self, model: ChatModel) -> None:
        self.model = model

    def evaluate(self, state: SessionState | list[ConversationTurn] | str) -> MITIFidelityReport:
        transcript = self._transcript_text(state)
        raw = self.model.complete(
            [
                {"role": "system", "content": MI_STYLE_GUIDE + "\n" + MITI_FIDELITY_JSON_PROMPT},
                {"role": "user", "content": f"Transcript:\n{transcript}"},
            ],
            temperature=0.0,
        )
        return parse_miti_report(parse_json_object(raw))

    @staticmethod
    def _transcript_text(state: SessionState | list[ConversationTurn] | str) -> str:
        if isinstance(state, str):
            return state.strip()
        if isinstance(state, SessionState):
            turns = state.turns
        else:
            turns = state
        return "\n".join(f"{turn.speaker}: {turn.text}" for turn in turns)


def parse_miti_report(data: dict) -> MITIFidelityReport:
    parsed_ratings = [_parse_rating(item) for item in data.get("dimension_ratings", [])]
    ratings_by_dimension = {rating.dimension: rating for rating in parsed_ratings}
    ratings = tuple(
        ratings_by_dimension.get(
            dimension,
            MITIDimensionRating(
                dimension=dimension,
                score=1,
                concerns=("Missing dimension rating from evaluator output.",),
            ),
        )
        for dimension in MITIDimension
    )

    overall_score = float(data.get("overall_score", _average_score(ratings)))
    return MITIFidelityReport(
        overall_score=round(max(1.0, min(5.0, overall_score)), 2),
        adherent=bool(data.get("adherent", overall_score >= 4.0 and _minimum_score(ratings) >= 3)),
        summary=str(data.get("summary", "")).strip(),
        dimension_ratings=ratings,
        priority_recommendations=_string_tuple(data.get("priority_recommendations", ())),
    )


def _parse_rating(data: dict) -> MITIDimensionRating:
    dimension = MITIDimension(str(data.get("dimension", "")).strip())
    score = int(data.get("score", 1))
    return MITIDimensionRating(
        dimension=dimension,
        score=max(1, min(5, score)),
        strengths=_string_tuple(data.get("strengths", ())),
        concerns=_string_tuple(data.get("concerns", ())),
        evidence=_string_tuple(data.get("evidence", ())),
    )


def _string_tuple(items: object) -> tuple[str, ...]:
    if not isinstance(items, list | tuple):
        return ()
    return tuple(str(item).strip() for item in items if str(item).strip())


def _average_score(ratings: tuple[MITIDimensionRating, ...]) -> float:
    return sum(rating.score for rating in ratings) / len(ratings)


def _minimum_score(ratings: tuple[MITIDimensionRating, ...]) -> int:
    return min(rating.score for rating in ratings)
