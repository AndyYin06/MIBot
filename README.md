# MI Smoking Cessation Counsellor

A command-line motivational interviewing (MI) counsellor prototype for smoking cessation. The app starts the conversation, alternates turns with the user, tracks motivational and safety state, and checks each generated response before it reaches the CLI.

The default runtime is deterministic and local, so the project works without network access or API keys. An OpenAI-compatible chat completion endpoint can be enabled for live model-backed counselling, judging, and MITI-style transcript review.

## What It Does

- Runs an interactive smoking cessation counselling session in the terminal.
- Uses an LLM-backed classifier for medical scope, out-of-scope topics, and persuasive misuse, with a minimal deterministic crisis precheck for urgent risk.
- Tracks change talk, sustain talk, ambivalence, discord, readiness hints, rapport, goal alignment, and stagnation.
- Estimates the active MI task as engaging, focusing, evoking, or planning without forcing a linear stage progression.
- Drafts concise MI-consistent responses and validates them before display.
- Falls back to conservative scripted responses when safety, scope, or MI fidelity checks fail.
- Provides `/state` diagnostics and `/miti` transcript-level fidelity reporting.

## Repository Layout

```text
mi_counsellor/
  cli.py          CLI loop, commands, engine construction, report formatting
  classifiers.py  Safety/scope, motivational language, process, and dynamics analyzers
  counsellor.py   Drafting, judge validation, crisis validation, fallback policy, engine
  domain.py       Dataclasses and enums for session state and MITI reports
  llm.py          Demo model, OpenAI-compatible model adapter, JSON parsing
  miti.py         MITI-informed evaluator and local micro-metric analyzer
  prompts.py      MI style guide and JSON prompt contracts
tests/            Unit tests for classifiers, CLI formatting, judge behavior, and MITI metrics
docs/             Design notes and validation feature notes
tools/            Utility script for extracting non-verbatim source notes from an MI PDF
```

## Install

This project requires Python 3.11 or newer. With `uv`:

```bash
uv sync
```

The only runtime dependency is `pypdf`, used by the source-note extraction tool. Tests use `pytest` from the development dependency group.

## Run

Local deterministic demo mode:

```bash
uv run python -m mi_counsellor
```

The package also defines a console script:

```bash
uv run mi-counsellor
```

OpenAI-compatible mode:

```bash
export MI_LLM_PROVIDER=openai-compatible
export OPENAI_API_KEY=...
export MI_COUNSELLOR_MODEL=gpt-4o-mini
export MI_JUDGE_MODEL=gpt-4o-mini
export MI_MITI_MODEL=gpt-4o-mini
uv run mi-counsellor
```

Optional endpoint override:

```bash
export OPENAI_BASE_URL=https://api.openai.com/v1
```

## CLI Commands

- `/state` prints the current safety, motivational language, MI process, and session dynamics state as JSON.
- `/miti` prints a transcript-level MI fidelity report with 1-5 dimension scores and local validation metrics.
- `/quit`, `/exit`, `quit`, or `exit` ends the session.

## Testing

```bash
uv run pytest
```

The current tests cover:

- crisis precheck behavior, model-backed safety/scope parsing, ambivalence, readiness, discord, and stagnation classification;
- process-state movement back to engaging when discord appears;
- local judge rejection for unpermitted advice and incomplete crisis handling;
- MITI report parsing, score clamping, formatting, micro-metrics, and drift signals.

## Safety

This is a prototype educational tool, not medical care. It does not diagnose, prescribe, provide medication dosing, or replace a clinician, quitline, crisis service, or emergency support. Direct urgent-risk language bypasses generation and returns a crisis-oriented support message. Medical or medication content is classified by the safety/scope model and handled with supportive reflection and referral to qualified help.

The tool is scoped to smoking cessation, nicotine harm reduction, and autonomy-respecting health support. It blocks attempts to use MI for manipulative persuasion, selling harmful products, or bypassing safety boundaries.

## Design Notes

See [docs/design.md](docs/design.md) for the architecture, runtime flow, state model, guardrails, and extension points.
