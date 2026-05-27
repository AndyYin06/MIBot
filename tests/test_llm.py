import json

import mi_counsellor.llm as llm
from mi_counsellor.llm import OpenAICompatibleChatModel


class FakeStreamingResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines

    def __enter__(self) -> "FakeStreamingResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def __iter__(self):
        return iter(self.lines)


def test_openai_compatible_model_streams_chat_completion_deltas(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeStreamingResponse(
            [
                b"data: " + json.dumps({"choices": [{"delta": {"content": "That "}}]}).encode("utf-8") + b"\n",
                b"data: " + json.dumps({"choices": [{"delta": {"content": "sounds"}}]}).encode("utf-8") + b"\n",
                b"data: " + json.dumps({"choices": [{"delta": {}}]}).encode("utf-8") + b"\n",
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    model = OpenAICompatibleChatModel(model="test-model", api_key="key", timeout_seconds=3)

    chunks = list(model.stream_complete([{"role": "user", "content": "hello"}], temperature=0.2))

    assert chunks == ["That ", "sounds"]
    request, timeout = requests[0]
    assert timeout == 3
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_obfuscation": False}
