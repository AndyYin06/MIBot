from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class ChatModel(Protocol):
    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        ...


@dataclass
class OpenAICompatibleChatModel:
    model: str
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 45

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        return data["choices"][0]["message"]["content"]


class DemoChatModel:
    """Local deterministic stand-in used when no LLM credentials are configured."""

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        joined = "\n".join(message["content"] for message in messages[-3:])
        if '"safe"' in joined and '"mi_consistent"' in joined:
            return json.dumps(
                {
                    "safe": True,
                    "mi_consistent": True,
                    "premature_advice": False,
                    "premature_planning": False,
                    "handles_scope": True,
                    "problems": [],
                    "repair_instruction": "",
                }
            )
        if "Current safety/scope assessment: caution" in joined:
            response = (
                "That sounds important, and I want to be careful with medical details. "
                "A clinician or quitline can help with medication or health-specific choices. "
                "What would you like to sort through here about your own reasons for changing, if any?"
            )
        elif "Current motivational language: discord" in joined:
            response = (
                "You are right to say so if this is feeling off. This is your choice, and I do not want to push. "
                "What would make this conversation feel more useful to you?"
            )
        elif "Current motivational language: sustain_talk" in joined:
            response = (
                "Smoking sounds like it is serving a real purpose for you. "
                "What do you like about it, and what, if anything, worries you about keeping things as they are?"
            )
        elif "Current motivational language: ambivalence" in joined:
            response = (
                "Part of you can see reasons to change, and part of you has good reasons not to rush it. "
                "What feels like the strongest reason on each side right now?"
            )
        elif "Current MI process task: planning" in joined:
            response = (
                "It sounds like there may be some readiness there. "
                "Would it be okay to talk through what a first small step could look like, while keeping it fully your choice?"
            )
        elif "Current MI process task: focusing" in joined:
            response = (
                "There are a few directions we could go with this. "
                "Would it be useful to focus on what smoking is doing for you right now, or on what has you wondering about change?"
            )
        else:
            response = (
                "It sounds like smoking has a real place in your day, and part of you is wondering what it might be like if that changed. "
                "What feels most important to understand about your smoking right now?"
            )
        return json.dumps(
            {
                "response": response,
                "intent": "use the current MI state to reflect and evoke without premature planning",
                "mi_task_used": "evoking",
            }
        )


def build_chat_model(env_prefix: str, default_model: str) -> ChatModel:
    provider = os.getenv("MI_LLM_PROVIDER", "demo").lower()
    if provider in {"openai", "openai-compatible"}:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when MI_LLM_PROVIDER=openai-compatible.")
        model = os.getenv(env_prefix, default_model)
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatibleChatModel(model=model, api_key=api_key, base_url=base_url)
    return DemoChatModel()


def parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in model output: {raw[:200]}")
    return json.loads(text[start : end + 1])
