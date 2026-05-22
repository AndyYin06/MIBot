# MI Smoking Cessation Counsellor

A CLI motivational interviewing counsellor for smoking cessation. The counsellor speaks first, then alternates turns with the user.

The implementation is intentionally modular:

- `SafetyScopeClassifier` detects crisis, medical, age/legal, and out-of-scope content.
- `MotivationalLanguageClassifier` tracks change talk, sustain talk, ambivalence, discord, and confidence signals.
- `SessionDynamicsAnalyzer` tracks multi-turn rapport, goal alignment, motivational direction, and stagnation.
- `MIProcessStateIdentifier` estimates the current MI task from conversation evidence rather than pushing a linear stage progression.
- `Counsellor` drafts the next MI-consistent response.
- `Judge` validates safety and MI fidelity before anything is shown to the user.
- `FallbackPolicy` repairs or replaces responses that are unsafe, too directive, premature, or outside scope.

## Run

```bash
python3 -m mi_counsellor
```

By default the app runs in a deterministic local demo mode so the CLI works without network access or API keys.

To use an OpenAI-compatible chat completion endpoint:

```bash
export MI_LLM_PROVIDER=openai-compatible
export OPENAI_API_KEY=...
export MI_COUNSELLOR_MODEL=gpt-4o-mini
export MI_JUDGE_MODEL=gpt-4o-mini
python3 -m mi_counsellor
```

Optional:

```bash
export OPENAI_BASE_URL=https://api.openai.com/v1
```

## Commands

- `/state` prints the internal motivational and process state.
- `/state` also shows session dynamics used for pacing and strategy selection.
- `/quit` exits.

## Safety

This is a prototype educational tool, not medical care. It avoids medication dosing, diagnosis, or emergency handling beyond supportive triage language and encourages qualified professional or emergency help when needed.
