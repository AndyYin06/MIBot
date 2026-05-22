# Design

This project is a command-line motivational interviewing (MI) counsellor for smoking cessation. It uses a gated generation loop: each user turn is classified, session state is updated, a counsellor response is drafted, and a judge validates the draft before anything is shown to the user.

The implementation is deliberately rule-first around safety, scope, process state, and local fidelity checks. That keeps the demo deterministic, makes clinical guardrails inspectable, and leaves clear places to swap in stronger model-backed or corpus-trained components later.

## Goals

- Keep the conversation focused on smoking cessation and nicotine-related change.
- Preserve MI spirit: partnership, acceptance, compassion, empowerment, and autonomy.
- Prefer reflections and open questions over advice, confrontation, pressure, or premature planning.
- Treat engaging, focusing, evoking, and planning as revisitable MI tasks rather than fixed stages.
- Detect urgent risk and scope problems before generation.
- Validate generated responses for safety, MI consistency, concision, and ethical context.
- Provide transparent diagnostics through `/state` and `/miti`.

## Runtime Flow

```text
CLI input
  -> append user turn to SessionState
  -> SafetyScopeClassifier
  -> MotivationalLanguageClassifier
  -> SessionDynamicsAnalyzer
  -> MIProcessStateIdentifier
  -> MIEngine
       -> urgent/out-of-scope? use FallbackPolicy immediately
       -> Counsellor drafts JSON response through ChatModel
       -> Judge evaluates model result plus local validation checks
       -> accepted response, repaired response, or conservative fallback
  -> append counsellor turn to SessionState
  -> print response
```

The CLI also supports diagnostic commands that do not add user turns:

- `/state` formats the live `SessionState` as JSON.
- `/miti` runs transcript-level fidelity evaluation and local micro-metrics.
- `/quit` exits the session.

## Core Modules

`mi_counsellor.cli` wires the application together. It creates classifiers, the engine, and the MITI validator; owns the input loop; and formats `/state` and `/miti` output.

`mi_counsellor.domain` defines the shared dataclasses and enums: safety level, MI task, motivational talk type, session dynamics, transcript turns, process assessment, and MITI report structures.

`mi_counsellor.classifiers` contains transparent rule-based analyzers:

- `SafetyScopeClassifier` detects urgent risk, medical caution scope, out-of-scope topics, and persuasive misuse.
- `MotivationalLanguageClassifier` identifies change talk, sustain talk, ambivalence, discord, and readiness hints.
- `SessionDynamicsAnalyzer` tracks rapport, goal alignment, motivational direction, consecutive sustain talk or discord, stagnation, and a recommended next strategy.
- `MIProcessStateIdentifier` estimates the current MI task from the latest language, conversation length, and dynamics.

`mi_counsellor.counsellor` contains the response path:

- `Counsellor` builds a state-rich prompt and asks the configured `ChatModel` for JSON.
- `Judge` evaluates a candidate response with the model judge and local validators.
- `CrisisProtocolValidator` checks urgent-risk replies for concrete safety behaviors.
- `FallbackPolicy` returns conservative scoped responses when generation or validation fails.
- `MIEngine` coordinates drafting, one repair attempt, and fallback.

`mi_counsellor.llm` provides the model boundary. `DemoChatModel` is deterministic and local. `OpenAICompatibleChatModel` calls `/chat/completions` with `urllib` when `MI_LLM_PROVIDER=openai-compatible`.

`mi_counsellor.miti` provides transcript-level fidelity evaluation. It combines a model-generated MITI-informed report with `MITIMicroMetricAnalyzer`, which counts reflections, questions, complex-reflection markers, advice without nearby permission, average counsellor length, and drift signals.

`mi_counsellor.prompts` holds the MI style guide and JSON contracts for counsellor, judge, and MITI evaluator outputs.

## State Model

`SessionState` stores the ordered transcript plus four live assessments:

- `SafetyAssessment`: `ok`, `caution`, `urgent`, or `out_of_scope`, with reasons and an optional suggested response.
- `LanguageAssessment`: dominant talk type, evidence markers, readiness hint, and confidence.
- `ProcessAssessment`: active MI task, confidence, rationale, and a `slow_down` flag.
- `SessionDynamics`: rapport, goal alignment, motivation direction, repeated sustain talk or discord counts, stagnation, and recommended next strategy.

The process identifier can move backward. Discord or relational strain returns the system to engaging; sustain talk and ambivalence keep it in evoking; planning appears only when readiness or commitment language is present.

## Safety and Scope

Safety and scope checks happen before any generated response is accepted.

Urgent-risk language, including self-harm, violence, overdose, breathing emergencies, chest pain, or heart-attack language, bypasses generation and returns a crisis-oriented support message with emergency or 988 guidance.

Medical and medication topics are classified as caution scope. The counsellor may reflect and support motivation, but it must not diagnose, prescribe, or provide dosing instructions. It redirects medical specifics to a clinician or quitline.

Out-of-scope requests are redirected to smoking, nicotine, motivation, and quitting. Attempts to use MI for selling, manipulating, promoting harmful products, or bypassing ethical guardrails are blocked as persuasive misuse.

## Generation and Validation

The counsellor prompt includes the recent transcript, safety assessment, MI task, motivational language markers, session dynamics, and repair instructions when applicable. It asks for JSON with a response, intent, and MI task used.

The judge evaluates the candidate response for:

- basic safety;
- MI consistency;
- uninvited advice;
- premature planning;
- scope handling;
- concision;
- ethical context.

The judge result is accepted only if all required checks pass. Local validation supplements the model judge by rejecting incomplete crisis responses, advice or direction without nearby permission, verbosity over the single-turn threshold, and drift signals after longer conversations.

If the first draft fails, the engine sends the judge's repair instruction back for one repair attempt. If repair fails or the model path errors, `FallbackPolicy` chooses a conservative response from the current safety, language, process, and dynamics state.

## MITI-Informed Validation

The `/miti` command evaluates the transcript with six dimensions:

- cultivating change talk;
- softening sustain talk;
- partnership;
- empathy;
- autonomy support;
- avoiding persuasion or advice without permission.

The model-backed report returns 1-5 scores, strengths, concerns, evidence, and priority recommendations. The local micro-metric analyzer adds observable counts so the report can catch behavioral drift that might not show up in a single model rating.

The local metrics are intentionally approximate. They are not a replacement for formal MITI coding, but they are useful regression signals for a prototype.

## Textbook-Grounded MI Principles

The design is based on non-verbatim principles extracted from a motivational interviewing source text:

- MI is a collaborative conversation about change and growth that strengthens the user's own motivation and commitment.
- The four MI tasks are engaging, focusing, evoking, and planning.
- OARS skills support engagement: open questions, affirming, reflecting, and summarizing.
- Sustain talk is language against change and often reflects normal ambivalence.
- Discord signals discomfort in the helping relationship, and counsellor responses can increase or decrease it.
- Advice and information can fit MI only when offered in a person-centered way, typically with permission and without overriding autonomy.
- The 4th edition prefers "fixing reflex" for what older MI writing called the "righting reflex."

The helper script at `tools/extract_mi_source_notes.py` extracts source-note snippets from a local PDF for development notes. It is not part of the CLI runtime.

## Testing Strategy

The test suite focuses on behavior at the seams where regressions would matter most:

- safety, scope, persuasive misuse, ambivalence, readiness, discord, and stagnation classification;
- MI process transitions, especially returning to engaging when discord appears;
- judge rejection of unpermitted advice and incomplete crisis responses;
- MITI report parsing, score clamping, human-readable formatting, local micro-metrics, and drift flags.

Because the default model is deterministic, tests do not require network access or model credentials.

## Extension Points

Likely next improvements:

- Replace selected rule-based classifiers with trained or evaluated classifiers while preserving the same dataclass outputs.
- Expand safety and scope tests with adversarial prompt variants.
- Add richer transcript fixtures for longer-session MITI drift testing.
- Persist sessions for replay and regression evaluation.
- Add structured logging around judge rejection reasons and fallback paths.
- Introduce provider-specific adapters behind the `ChatModel` protocol if more than the OpenAI-compatible API is needed.
