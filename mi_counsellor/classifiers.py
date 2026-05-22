from __future__ import annotations

import re

from mi_counsellor.domain import (
    LanguageAssessment,
    MITask,
    MotivationDirection,
    ProcessAssessment,
    SafetyAssessment,
    SafetyLevel,
    SessionDynamics,
    SessionState,
    TalkType,
)


class SafetyScopeClassifier:
    """Rule-first safety classifier with conservative scope boundaries."""

    _urgent_patterns = (
        r"\b(kill myself|suicide|suicidal|end my life|hurt myself|self harm)\b",
        r"\b(overdose|poison|can't breathe|chest pain|heart attack)\b",
        r"\b(violent|hurt someone|kill someone)\b",
    )
    _medical_patterns = (
        r"\b(pregnant|pregnancy|nicotine patch|varenicline|chantix|bupropion|zyban)\b",
        r"\b(dose|dosage|withdrawal seizure|medication|prescription)\b",
    )
    _out_of_scope_patterns = (
        r"\b(homework|tax|legal advice|invest|portfolio|code|programming)\b",
    )
    _persuasive_misuse_patterns = (
        r"\b(sell|sales|marketing|advertis(e|ing)|convince|persuade|manipulate)\b.*\b(cigarettes?|tobacco|vapes?|nicotine|alcohol|drugs?)\b",
        r"\b(cigarettes?|tobacco|vapes?|nicotine|alcohol|drugs?)\b.*\b(sell|sales|marketing|advertis(e|ing)|convince|persuade|manipulate)\b",
    )

    def classify(self, text: str) -> SafetyAssessment:
        lower = text.lower()
        if self._matches(lower, self._urgent_patterns):
            return SafetyAssessment(
                SafetyLevel.URGENT,
                ("urgent_risk",),
                "Thank you for telling me. Your safety matters more than quitting smoking right now. "
                "If you might hurt yourself or someone else, please call emergency services now, or call/text 988 "
                "in the U.S. or Canada for immediate crisis support. Is there someone nearby you can be with while you get support?",
            )
        if self._matches(lower, self._persuasive_misuse_patterns):
            return SafetyAssessment(
                SafetyLevel.OUT_OF_SCOPE,
                ("persuasive_misuse_risk",),
                "I cannot help use motivational interviewing to sell, promote, or pressure people toward harmful products. "
                "I can help with smoking cessation support, reducing nicotine harm, or a non-manipulative health conversation.",
            )
        if self._matches(lower, self._medical_patterns):
            return SafetyAssessment(
                SafetyLevel.CAUTION,
                ("medical_or_medication_scope",),
            )
        if self._matches(lower, self._out_of_scope_patterns):
            return SafetyAssessment(
                SafetyLevel.OUT_OF_SCOPE,
                ("outside_smoking_cessation_scope",),
                "I may not be the right tool for that topic. I can stay with smoking, nicotine, motivation, and change around quitting. "
                "What, if anything, is on your mind about smoking today?",
            )
        return SafetyAssessment(SafetyLevel.OK)

    @staticmethod
    def _matches(text: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)


class MotivationalLanguageClassifier:
    change_patterns = (
        r"\b(i want|i wish|i'd like|i need|i have to|i should|i could|i can|i might)\b",
        r"\b(quit|stop|cut down|breathe better|save money|healthier|ready|try)\b",
    )
    sustain_patterns = (
        r"\b(i enjoy|i like|helps me|calms me|stress|not ready|can't|cannot|won't|too hard)\b",
        r"\b(after meals|with coffee|breaks|friends smoke|cravings)\b",
    )
    discord_patterns = (
        r"\b(you don't understand|stop telling me|whatever|leave me alone|judg)\b",
        r"\b(this is pointless|not helpful|annoying)\b",
    )
    high_readiness_patterns = (r"\b(today|this week|ready|plan|set a date|start now)\b",)
    low_readiness_patterns = (r"\b(not ready|someday|maybe later|don't want|no reason)\b",)

    def classify(self, text: str) -> LanguageAssessment:
        lower = text.lower()
        change = self._find(lower, self.change_patterns)
        sustain = self._find(lower, self.sustain_patterns)
        discord = self._find(lower, self.discord_patterns)

        if discord:
            dominant = TalkType.DISCORD
        elif change and sustain:
            dominant = TalkType.AMBIVALENCE
        elif change:
            dominant = TalkType.CHANGE
        elif sustain:
            dominant = TalkType.SUSTAIN
        else:
            dominant = TalkType.NEUTRAL

        high_readiness = self._find(lower, self.high_readiness_patterns)
        low_readiness = self._find(lower, self.low_readiness_patterns)
        readiness = "unknown"
        if low_readiness:
            readiness = "low"
        elif high_readiness:
            readiness = "high"
        elif change and sustain:
            readiness = "mixed"
        elif sustain:
            readiness = "low"

        evidence_count = len(change) + len(sustain) + len(discord)
        confidence = min(0.9, 0.35 + 0.12 * evidence_count)
        return LanguageAssessment(
            dominant=dominant,
            change_markers=tuple(change[:4]),
            sustain_markers=tuple(sustain[:4]),
            discord_markers=tuple(discord[:4]),
            confidence=confidence,
            readiness_hint=readiness,  # type: ignore[arg-type]
        )

    @staticmethod
    def _find(text: str, patterns: tuple[str, ...]) -> list[str]:
        hits: list[str] = []
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                hits.append(match.group(0))
        return hits


class MIProcessStateIdentifier:
    """Estimates the current MI task from evidence; does not force progression."""

    def identify(self, state: SessionState) -> ProcessAssessment:
        language = state.language
        dynamics = state.dynamics
        turn_count = state.user_turn_count()

        if turn_count <= 1:
            return ProcessAssessment(MITask.ENGAGING, 0.75, "Early conversation; prioritize rapport and autonomy.")

        if language.dominant == TalkType.DISCORD:
            return ProcessAssessment(MITask.ENGAGING, 0.85, "Discord is present; repair engagement before moving on.", True)

        if dynamics.rapport == "strained" or dynamics.goal_alignment == "misaligned":
            return ProcessAssessment(
                MITask.ENGAGING,
                0.78,
                "Relational strain or goal misalignment is present; rebuild partnership before evoking change.",
                True,
            )

        if dynamics.stagnant:
            return ProcessAssessment(
                MITask.EVOKING,
                0.72,
                "Motivational direction has stalled; change strategy and evoke values or exceptions.",
                True,
            )

        if language.dominant in {TalkType.SUSTAIN, TalkType.AMBIVALENCE}:
            return ProcessAssessment(
                MITask.EVOKING,
                0.7,
                "Sustain talk or ambivalence is active; explore both sides and evoke values.",
                True,
            )

        if language.readiness_hint == "high" and language.dominant == TalkType.CHANGE:
            return ProcessAssessment(
                MITask.PLANNING,
                0.65,
                "User is offering readiness or implementation language; planning may be appropriate with permission.",
            )

        if turn_count >= 2 and language.dominant == TalkType.NEUTRAL:
            return ProcessAssessment(MITask.FOCUSING, 0.6, "Topic needs gentle focusing around smoking cessation.")

        return ProcessAssessment(MITask.EVOKING, 0.55, "Some change language is present; evoke before planning.")


class SessionDynamicsAnalyzer:
    """Tracks long-horizon conversational signals without replacing turn classifiers."""

    def update(self, state: SessionState) -> SessionDynamics:
        previous = state.dynamics
        language = state.language
        text = self._latest_user_text(state).lower()

        consecutive_sustain = self._next_count(
            previous.consecutive_sustain_turns,
            language.dominant in {TalkType.SUSTAIN, TalkType.AMBIVALENCE},
        )
        consecutive_discord = self._next_count(previous.consecutive_discord_turns, language.dominant == TalkType.DISCORD)

        if language.dominant == TalkType.DISCORD or consecutive_discord:
            rapport = "strained"
        elif language.dominant == TalkType.CHANGE and previous.rapport != "strained":
            rapport = "strong"
        else:
            rapport = "steady"

        if language.dominant == TalkType.DISCORD or self._mentions_bad_fit(text):
            goal_alignment = "misaligned"
        elif self._mentions_smoking_or_change(text):
            goal_alignment = "aligned"
        else:
            goal_alignment = previous.goal_alignment if state.user_turn_count() > 1 else "unclear"

        motivation_direction = self._direction_for(language)
        stagnant = consecutive_sustain >= 2 or consecutive_discord >= 2
        strategy = self._strategy_for(rapport, goal_alignment, motivation_direction, stagnant)

        return SessionDynamics(
            rapport=rapport,
            goal_alignment=goal_alignment,
            motivation_direction=motivation_direction,
            consecutive_sustain_turns=consecutive_sustain,
            consecutive_discord_turns=consecutive_discord,
            stagnant=stagnant,
            recommended_strategy=strategy,
        )

    @staticmethod
    def _latest_user_text(state: SessionState) -> str:
        for turn in reversed(state.turns):
            if turn.speaker == "user":
                return turn.text
        return ""

    @staticmethod
    def _next_count(previous: int, active: bool) -> int:
        return previous + 1 if active else 0

    @staticmethod
    def _direction_for(language: LanguageAssessment) -> MotivationDirection:
        if language.dominant == TalkType.CHANGE:
            return MotivationDirection.TOWARD_CHANGE
        if language.dominant == TalkType.SUSTAIN:
            return MotivationDirection.AWAY_FROM_CHANGE
        if language.dominant == TalkType.AMBIVALENCE:
            return MotivationDirection.MIXED
        return MotivationDirection.NEUTRAL

    @staticmethod
    def _mentions_smoking_or_change(text: str) -> bool:
        return bool(re.search(r"\b(smok(e|ing)|cigarette|tobacco|nicotine|quit|stop|cut down|change)\b", text))

    @staticmethod
    def _mentions_bad_fit(text: str) -> bool:
        return bool(re.search(r"\b(not helpful|pointless|wrong topic|not what i asked|you don't understand)\b", text))

    @staticmethod
    def _strategy_for(
        rapport: str,
        goal_alignment: str,
        direction: MotivationDirection,
        stagnant: bool,
    ) -> str:
        if rapport == "strained" or goal_alignment == "misaligned":
            return "repair rapport, affirm autonomy, and ask what would make the conversation useful"
        if stagnant:
            return "change strategy with a double-sided reflection and evoke values or exceptions"
        if direction == MotivationDirection.TOWARD_CHANGE:
            return "reinforce change talk with a complex reflection before asking permission to plan"
        if direction == MotivationDirection.AWAY_FROM_CHANGE:
            return "reflect sustain talk accurately and invite the other side without arguing"
        if direction == MotivationDirection.MIXED:
            return "use a double-sided reflection and ask which side feels stronger"
        return "reflect and ask one open question"
