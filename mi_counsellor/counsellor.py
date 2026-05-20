from __future__ import annotations

from dataclasses import dataclass

from mi_counsellor.domain import SafetyLevel, SessionState, TalkType
from mi_counsellor.llm import ChatModel, parse_json_object
from mi_counsellor.prompts import COUNSELLOR_JSON_PROMPT, JUDGE_JSON_PROMPT, MI_STYLE_GUIDE


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
        )


class Counsellor:
    def __init__(self, model: ChatModel) -> None:
        self.model = model

    def opening(self) -> str:
        return (
            "Hi, I am here to talk with you about smoking in a way that does not push or judge. "
            "What would you like me to understand about your smoking right now?"
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

Smoking cessation is the focus. Do not give a quit plan unless the user has shown readiness and you ask permission.
If caution scope is present, be supportive and suggest a qualified clinician for medical specifics.
{f"Repair the prior response using this instruction: {repair_instruction}" if repair_instruction else ""}

{COUNSELLOR_JSON_PROMPT}
"""


class Judge:
    def __init__(self, model: ChatModel) -> None:
        self.model = model

    def evaluate(self, state: SessionState, draft: DraftResponse) -> JudgeResult:
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

Candidate response:
{draft.text}
""",
                },
            ],
            temperature=0.0,
        )
        data = parse_json_object(raw)
        return JudgeResult(
            safe=bool(data.get("safe", False)),
            mi_consistent=bool(data.get("mi_consistent", False)),
            premature_advice=bool(data.get("premature_advice", True)),
            premature_planning=bool(data.get("premature_planning", True)),
            handles_scope=bool(data.get("handles_scope", False)),
            problems=tuple(str(item) for item in data.get("problems", [])),
            repair_instruction=str(data.get("repair_instruction", "")).strip(),
        )


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

        if state.language.dominant == TalkType.DISCORD:
            return (
                "You are right to push back if this feels like pressure. This is your choice. "
                "What would make this conversation feel more useful, or would you rather simply talk through what smoking does for you?"
            )

        if state.language.dominant == TalkType.SUSTAIN:
            return (
                "Smoking is doing something for you, especially when things are stressful. "
                "What do you like about it, and what, if anything, concerns you about keeping things the same?"
            )

        if state.process.slow_down:
            return (
                "There are a few mixed pieces here, so I do not want to rush you into a plan. "
                "What feels most true for you right now about smoking and the possibility of changing it?"
            )

        suffix = ""
        if judge and judge.problems:
            suffix = " "
        return (
            "Let me slow down and stay with your perspective."
            f"{suffix}What matters most to you about smoking right now?"
        )


class MIEngine:
    def __init__(self, counsellor: Counsellor, judge: Judge, fallback: FallbackPolicy) -> None:
        self.counsellor = counsellor
        self.judge = judge
        self.fallback = fallback

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
