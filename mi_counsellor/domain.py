from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class SafetyLevel(str, Enum):
    OK = "ok"
    CAUTION = "caution"
    URGENT = "urgent"
    OUT_OF_SCOPE = "out_of_scope"


class MITask(str, Enum):
    ENGAGING = "engaging"
    FOCUSING = "focusing"
    EVOKING = "evoking"
    PLANNING = "planning"


class TalkType(str, Enum):
    CHANGE = "change_talk"
    SUSTAIN = "sustain_talk"
    AMBIVALENCE = "ambivalence"
    DISCORD = "discord"
    NEUTRAL = "neutral"


class MotivationDirection(str, Enum):
    TOWARD_CHANGE = "toward_change"
    AWAY_FROM_CHANGE = "away_from_change"
    MIXED = "mixed"
    NEUTRAL = "neutral"
class MITIDimension(str, Enum):
    CULTIVATING_CHANGE_TALK = "cultivating_change_talk"
    SOFTENING_SUSTAIN_TALK = "softening_sustain_talk"
    PARTNERSHIP = "partnership"
    EMPATHY = "empathy"
    AUTONOMY_SUPPORT = "autonomy_support"
    AVOIDING_UNPERMITTED_ADVICE = "avoiding_unpermitted_advice"


@dataclass(frozen=True)
class SafetyAssessment:
    level: SafetyLevel
    reasons: tuple[str, ...] = ()
    suggested_response: str | None = None


@dataclass(frozen=True)
class LanguageAssessment:
    dominant: TalkType
    change_markers: tuple[str, ...] = ()
    sustain_markers: tuple[str, ...] = ()
    discord_markers: tuple[str, ...] = ()
    confidence: float = 0.5
    readiness_hint: Literal["low", "mixed", "high", "unknown"] = "unknown"


@dataclass(frozen=True)
class ProcessAssessment:
    task: MITask
    confidence: float
    rationale: str
    slow_down: bool = False


@dataclass(frozen=True)
class SessionDynamics:
    rapport: Literal["strong", "steady", "strained"] = "steady"
    goal_alignment: Literal["aligned", "unclear", "misaligned"] = "unclear"
    motivation_direction: MotivationDirection = MotivationDirection.NEUTRAL
    consecutive_sustain_turns: int = 0
    consecutive_discord_turns: int = 0
    stagnant: bool = False
    recommended_strategy: str = "reflect and ask one open question"
class MITIDimensionRating:
    dimension: MITIDimension
    score: int
    strengths: tuple[str, ...] = ()
    concerns: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class MITIFidelityReport:
    overall_score: float
    adherent: bool
    summary: str
    dimension_ratings: tuple[MITIDimensionRating, ...]
    priority_recommendations: tuple[str, ...] = ()


@dataclass
class ConversationTurn:
    speaker: Literal["user", "counsellor"]
    text: str


@dataclass
class SessionState:
    turns: list[ConversationTurn] = field(default_factory=list)
    safety: SafetyAssessment = field(default_factory=lambda: SafetyAssessment(SafetyLevel.OK))
    language: LanguageAssessment = field(default_factory=lambda: LanguageAssessment(TalkType.NEUTRAL))
    process: ProcessAssessment = field(
        default_factory=lambda: ProcessAssessment(MITask.ENGAGING, 0.6, "Opening contact.")
    )
    dynamics: SessionDynamics = field(default_factory=SessionDynamics)

    def add_turn(self, speaker: Literal["user", "counsellor"], text: str) -> None:
        self.turns.append(ConversationTurn(speaker=speaker, text=text.strip()))

    def transcript(self, max_turns: int = 10) -> str:
        recent = self.turns[-max_turns:]
        return "\n".join(f"{turn.speaker}: {turn.text}" for turn in recent)

    def user_turn_count(self) -> int:
        return sum(1 for turn in self.turns if turn.speaker == "user")
