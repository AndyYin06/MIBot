from __future__ import annotations

from dataclasses import dataclass

from mi_counsellor.domain import ConversationTurn, SafetyLevel, SessionState, TalkType
from mi_counsellor.llm import ChatModel, parse_json_object
from mi_counsellor.miti import MITIMicroMetricAnalyzer
from mi_counsellor.prompts import (
    COUNSELLOR_JSON_PROMPT,
    JUDGE_JSON_PROMPT,
    MI_RESPONSE_GUIDANCE,
    MI_STYLE_GUIDE,
    OPENING_JSON_PROMPT,
)


OPENING_FALLBACK = (
    "Hi, I'm glad you're here. "
    "What would you like me to understand about smoking in your life right now?"
)

OPENING_DISALLOWED_TERMS = (
    "push",
    "judg",
    "nonjudgmental",
    "non-judgmental",
    "motivational interviewing",
    "counselling technique",
    "counseling technique",
)


@dataclass(frozen=True)
class DraftResponse:
    text: str
    intent: str
    task_used: str


@dataclass(frozen=True)
class JudgeResult:
    safe: bool
    mi_consistent: bool
    premature_advice: bool
    premature_planning: bool
    handles_scope: bool
    concise: bool
    ethical_context_ok: bool
    problems: tuple[str, ...]
    repair_instruction: str

    @property
    def accepted(self) -> bool:
        return (
            self.safe
            and self.mi_consistent
            and not self.premature_advice
            and not self.premature_planning
            and self.handles_scope
            and self.concise
            and self.ethical_context_ok
        )


class Counsellor:
    def __init__(self, model: ChatModel) -> None:
        self.model = model

    def opening(self) -> str:
        return OPENING_FALLBACK

    def draft_opening(self, repair_instruction: str | None = None) -> DraftResponse:
        prompt = self._build_opening_prompt(repair_instruction)
        raw = self.model.complete(
            [
                {"role": "system", "content": MI_STYLE_GUIDE},
                {"role": "user", "content": prompt},
            ],
            temperature=0.55,
        )
        data = parse_json_object(raw)
        return DraftResponse(
            text=str(data.get("response", "")).strip(),
            intent=str(data.get("intent", "")).strip(),
            task_used=str(data.get("mi_task_used", "engaging")).strip(),
        )

    def draft(self, state: SessionState, repair_instruction: str | None = None) -> DraftResponse:
        prompt = self._build_prompt(state, repair_instruction)
        raw = self.model.complete(
            [
                {"role": "system", "content": MI_STYLE_GUIDE},
                {"role": "user", "content": prompt},
            ],
            temperature=0.45,
        )
        data = parse_json_object(raw)
        return DraftResponse(
            text=str(data.get("response", "")).strip(),
            intent=str(data.get("intent", "")).strip(),
            task_used=str(data.get("mi_task_used", "")).strip(),
        )

    def _build_prompt(self, state: SessionState, repair_instruction: str | None) -> str:
        return f"""
Conversation:
{state.transcript()}

Current safety/scope assessment: {state.safety.level.value}; reasons={state.safety.reasons}
Current MI process task: {state.process.task.value}; confidence={state.process.confidence}; rationale={state.process.rationale}; slow_down={state.process.slow_down}
Current motivational language: {state.language.dominant.value}; readiness={state.language.readiness_hint}; change={state.language.change_markers}; sustain={state.language.sustain_markers}; discord={state.language.discord_markers}
Current session dynamics: rapport={state.dynamics.rapport}; goal_alignment={state.dynamics.goal_alignment}; motivation_direction={state.dynamics.motivation_direction.value}; stagnant={state.dynamics.stagnant}; recommended_strategy={state.dynamics.recommended_strategy}

Smoking cessation is the focus. Do not give a quit plan unless the user has shown readiness and you ask permission.
If caution scope is present, be supportive and suggest a qualified clinician for medical specifics.
Keep this turn brief enough to invite continued conversation.
Use this guidance to adapt to the user's current behavior without sounding scripted:
{MI_RESPONSE_GUIDANCE}
{f"Repair the prior response using this instruction: {repair_instruction}" if repair_instruction else ""}

{COUNSELLOR_JSON_PROMPT}
"""

    def _build_opening_prompt(self, repair_instruction: str | None) -> str:
        return f"""
This is the first counsellor turn before the user has said anything.

Smoking cessation is the focus, but do not assume the user's readiness or reasons.
Start the conversation naturally and briefly.
Do not mention motivational interviewing, counselling technique, being nonjudgmental,
not judging, not being pushy, or similar meta-framing.
Keep the tone warm, human, non-clinical, and open-ended.
Invite the user's perspective rather than explaining the counsellor's stance.
{f"Repair the prior response using this instruction: {repair_instruction}" if repair_instruction else ""}

{OPENING_JSON_PROMPT}
"""


class Judge:
    def __init__(self, model: ChatModel) -> None:
        self.model = model

    def evaluate(self, state: SessionState, draft: DraftResponse) -> JudgeResult:
        local_problems = self._local_validation_problems(state, draft)
        raw = self.model.complete(
            [
                {"role": "system", "content": MI_STYLE_GUIDE + "\n" + JUDGE_JSON_PROMPT},
                {
                    "role": "user",
                    "content": f"""
Conversation:
{state.transcript()}

State:
safety={state.safety}
process={state.process}
language={state.language}

Response guidance:
{MI_RESPONSE_GUIDANCE}

Candidate response:
{draft.text}
""",
                },
            ],
            temperature=0.0,
        )
        data = parse_json_object(raw)
        model_problems = tuple(str(item) for item in data.get("problems", []))
        problems = model_problems + local_problems
        return JudgeResult(
            safe=bool(data.get("safe", False)) and not any("crisis protocol" in item for item in local_problems),
            mi_consistent=bool(data.get("mi_consistent", False)),
            premature_advice=bool(data.get("premature_advice", True))
            or any("permission" in item for item in local_problems),
            premature_planning=bool(data.get("premature_planning", True)),
            handles_scope=bool(data.get("handles_scope", False)),
            concise=bool(data.get("concise", self._is_concise(draft.text)))
            and not any("verbose" in item or "drift" in item for item in local_problems),
            ethical_context_ok=bool(data.get("ethical_context_ok", True)),
            problems=problems,
            repair_instruction=self._repair_instruction(str(data.get("repair_instruction", "")).strip(), local_problems),
        )

    @staticmethod
    def _is_concise(text: str) -> bool:
        words = text.split()
        sentence_count = sum(text.count(mark) for mark in ".?!")
        return len(words) <= 95 and sentence_count <= 5

    def _local_validation_problems(self, state: SessionState, draft: DraftResponse) -> tuple[str, ...]:
        if state.safety.level == SafetyLevel.URGENT:
            crisis = CrisisProtocolValidator().missing_behaviors(draft.text)
            if crisis:
                return (f"crisis protocol missing: {', '.join(crisis)}",)

        transcript = list(state.turns)
        transcript.append(ConversationTurn(speaker="counsellor", text=draft.text))
        analyzer = MITIMicroMetricAnalyzer()
        metrics = analyzer.analyze(transcript)
        problems: list[str] = []
        if self._draft_has_unpermitted_advice(state, draft, analyzer):
            problems.append("advice or direction appears without nearby permission")
        if len(draft.text.split()) > 95:
            problems.append("response is verbose for a single MI turn")
        if metrics.drift_flag and state.user_turn_count() >= 3:
            problems.append("local metrics suggest possible drift toward questions or verbosity")
        return tuple(problems)

    @staticmethod
    def _draft_has_unpermitted_advice(
        state: SessionState,
        draft: DraftResponse,
        analyzer: MITIMicroMetricAnalyzer,
    ) -> bool:
        if not analyzer._has_marker(draft.text, analyzer._advice_markers):
            return False
        context = " ".join(turn.text.lower() for turn in state.turns[-4:])
        return not analyzer._has_marker(context, analyzer._permission_markers)

    @staticmethod
    def _repair_instruction(model_instruction: str, local_problems: tuple[str, ...]) -> str:
        instructions = [model_instruction] if model_instruction else []
        if local_problems:
            instructions.append("; ".join(local_problems))
            instructions.append("Use one concise reflection plus one open question, and ask permission before advice.")
        return " ".join(instructions).strip()


class CrisisProtocolValidator:
    """Checks crisis replies for the five safety behaviors highlighted in validation research."""

    _checks = {
        "risk_acknowledgment": ("safety", "hurt yourself", "hurt someone", "risk", "emergency"),
        "empathy": ("thank you", "sorry", "sounds", "matters", "care"),
        "help_seeking": ("call", "text", "emergency services", "someone nearby", "clinician"),
        "specific_resources": ("988", "emergency services", "crisis"),
        "continued_engagement": ("is there", "can you", "would you", "while you", "nearby"),
    }

    def missing_behaviors(self, text: str) -> tuple[str, ...]:
        lower = text.lower()
        return tuple(name for name, markers in self._checks.items() if not any(marker in lower for marker in markers))

    def passes(self, text: str) -> bool:
        return not self.missing_behaviors(text)



class FallbackPolicy:
    def response(self, state: SessionState, judge: JudgeResult | None = None) -> str:
        if state.safety.suggested_response:
            return state.safety.suggested_response

        if state.safety.level == SafetyLevel.CAUTION:
            return (
                "That sounds important, and I want to stay in my lane with medical details. "
                "A clinician or quitline can help with medication or health-specific questions. "
                "What would feel useful to explore here about your own reasons for changing, if any?"
            )

        return (
            "I may be missing what matters most in this moment. "
            "What would you prefer to do from here?"
        )


class MIEngine:
    def __init__(self, counsellor: Counsellor, judge: Judge, fallback: FallbackPolicy) -> None:
        self.counsellor = counsellor
        self.judge = judge
        self.fallback = fallback

    def opening_response(self, state: SessionState) -> str:
        repair_instruction: str | None = None
        for _ in range(2):
            try:
                draft = self.counsellor.draft_opening(repair_instruction)
                if not draft.text:
                    break
                judge_result = self.judge.evaluate(state, draft)
            except Exception:
                break
            if judge_result.accepted and self._opening_text_allowed(draft.text):
                return draft.text
            repair_instruction = judge_result.repair_instruction or "; ".join(judge_result.problems)
            if not self._opening_text_allowed(draft.text):
                repair_instruction = (
                    f"{repair_instruction} Avoid explicit meta-language about not pushing, not judging, "
                    "being nonjudgmental, motivational interviewing, or counselling technique."
                ).strip()

        return self.counsellor.opening()

    def next_response(self, state: SessionState) -> str:
        if state.safety.level in {SafetyLevel.URGENT, SafetyLevel.OUT_OF_SCOPE}:
            return self.fallback.response(state)

        repair_instruction: str | None = None
        last_judge: JudgeResult | None = None
        for _ in range(2):
            draft = self.counsellor.draft(state, repair_instruction)
            if not draft.text:
                break
            last_judge = self.judge.evaluate(state, draft)
            if last_judge.accepted:
                return draft.text
            repair_instruction = last_judge.repair_instruction or "; ".join(last_judge.problems)

        return self.fallback.response(state, last_judge)

    @staticmethod
    def _opening_text_allowed(text: str) -> bool:
        lower = text.lower()
        return not any(term in lower for term in OPENING_DISALLOWED_TERMS)
