from __future__ import annotations

from mi_counsellor.domain import (
    MITIDimension,
    MITIDimensionRating,
    MITIFidelityReport,
    MITIMicroMetrics,
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
        report = parse_miti_report(parse_json_object(raw))
        return MITIFidelityReport(
            overall_score=report.overall_score,
            adherent=report.adherent,
            summary=report.summary,
            dimension_ratings=report.dimension_ratings,
            priority_recommendations=report.priority_recommendations,
            micro_metrics=MITIMicroMetricAnalyzer().analyze(state),
        )

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


class MITIMicroMetricAnalyzer:
    """Local transcript checks for MITI-style behavior counts and drift signals."""

    _reflection_markers = (
        "it sounds",
        "sounds like",
        "you feel",
        "you are",
        "you're",
        "you want",
        "you wish",
        "you value",
        "part of you",
        "smoking is",
        "smoking sounds",
        "that feels",
        "there is",
    )
    _complex_markers = (
        "part of you",
        "and at the same time",
        "while",
        "because",
        "underneath",
        "on one hand",
        "on the other hand",
        "protects",
        "costs",
        "matters",
    )
    _advice_markers = (
        "you should",
        "you need to",
        "you must",
        "throw out",
        "set a quit date",
        "use a patch",
        "take ",
        "call a quitline",
        "avoid ",
        "try ",
    )
    _permission_markers = (
        "would it be okay",
        "if you would like",
        "if you'd like",
        "with your permission",
        "can i",
        "may i",
        "would you like",
        "is it okay",
        "yes",
        "sure",
        "okay",
    )

    def analyze(self, state: SessionState | list[ConversationTurn] | str) -> MITIMicroMetrics:
        turns = self._turns(state)
        counsellor_texts = [turn.text for turn in turns if turn.speaker == "counsellor"]
        reflection_count = sum(self._count_reflections(text) for text in counsellor_texts)
        question_count = sum(text.count("?") for text in counsellor_texts)
        complex_count = sum(self._count_complex_reflections(text) for text in counsellor_texts)
        word_counts = [len(text.split()) for text in counsellor_texts]
        advice_count = self._count_advice_without_permission(turns)
        ratio = round(reflection_count / question_count, 2) if question_count else None
        complex_percent = round(complex_count / reflection_count * 100, 1) if reflection_count else 0.0
        average_words = round(sum(word_counts) / len(word_counts), 1) if word_counts else 0.0
        drift_flag = self._has_drift(word_counts, question_count, reflection_count)
        concerns = self._concerns(
            reflection_count,
            question_count,
            complex_percent,
            average_words,
            advice_count,
            drift_flag,
        )
        return MITIMicroMetrics(
            reflection_count=reflection_count,
            question_count=question_count,
            reflection_to_question_ratio=ratio,
            complex_reflection_count=complex_count,
            complex_reflection_percent=complex_percent,
            average_counsellor_words=average_words,
            advice_without_permission_count=advice_count,
            drift_flag=drift_flag,
            concerns=concerns,
        )

    def _turns(self, state: SessionState | list[ConversationTurn] | str) -> list[ConversationTurn]:
        if isinstance(state, SessionState):
            return state.turns
        if isinstance(state, list):
            return state
        turns: list[ConversationTurn] = []
        for line in state.splitlines():
            speaker, _, text = line.partition(":")
            if speaker.strip().lower() in {"user", "counsellor"}:
                turns.append(ConversationTurn(speaker=speaker.strip().lower(), text=text.strip()))  # type: ignore[arg-type]
        return turns

    def _count_reflections(self, text: str) -> int:
        sentences = self._sentences(text)
        return sum(1 for sentence in sentences if "?" not in sentence and self._has_marker(sentence, self._reflection_markers))

    def _count_complex_reflections(self, text: str) -> int:
        sentences = self._sentences(text)
        return sum(1 for sentence in sentences if "?" not in sentence and self._has_marker(sentence, self._complex_markers))

    def _count_advice_without_permission(self, turns: list[ConversationTurn]) -> int:
        count = 0
        prior_context = ""
        for turn in turns:
            text = turn.text.lower()
            if turn.speaker == "counsellor" and self._has_marker(text, self._advice_markers):
                if not self._has_marker(prior_context, self._permission_markers):
                    count += 1
            prior_context = f"{prior_context} {text}"[-500:]
        return count

    @staticmethod
    def _has_drift(word_counts: list[int], question_count: int, reflection_count: int) -> bool:
        if not word_counts:
            return False
        if sum(word_counts) / len(word_counts) > 85:
            return True
        if len(word_counts) >= 4:
            midpoint = len(word_counts) // 2
            early = sum(word_counts[:midpoint]) / midpoint
            late = sum(word_counts[midpoint:]) / (len(word_counts) - midpoint)
            if late > max(45, early * 1.8):
                return True
        return question_count >= max(4, reflection_count * 2)

    def _concerns(
        self,
        reflection_count: int,
        question_count: int,
        complex_percent: float,
        average_words: float,
        advice_count: int,
        drift_flag: bool,
    ) -> tuple[str, ...]:
        concerns: list[str] = []
        if question_count > reflection_count:
            concerns.append("Question count exceeds reflection count; MI may feel interrogative.")
        if reflection_count and complex_percent < 40.0:
            concerns.append("Complex reflection share is below the usual MITI good-practice target.")
        if average_words > 85:
            concerns.append("Counsellor turns are verbose on average.")
        if advice_count:
            concerns.append("Advice or direction appears without nearby permission.")
        if drift_flag:
            concerns.append("Local metrics suggest possible style drift or long-context degradation.")
        return tuple(concerns)

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [sentence.strip().lower() for sentence in text.replace("!", ".").split(".") if sentence.strip()]

    @staticmethod
    def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
        lower = text.lower()
        return any(marker in lower for marker in markers)


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
