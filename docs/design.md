# Design

This counsellor uses a gated generation loop rather than a single prompt. Each user turn is classified, the MI task estimate is updated, a counsellor response is drafted, and a judge validates the draft before it reaches the CLI.

## Textbook-Grounded MI Principles

The attached 4th edition PDF was inspected with `pypdf` after setting up `uv`. The design uses these non-verbatim source principles:

- MI is a collaborative conversation about change and growth that strengthens the user's own motivation and commitment.
- The four MI tasks are engaging, focusing, evoking, and planning. They can look sequential, but the system treats them as revisitable tasks, not forced stages.
- OARS skills support engagement: open questions, affirming, reflecting, and summarizing.
- Sustain talk is language against change and often reflects normal ambivalence.
- Discord is discomfort in the helping relationship; the counsellor response can increase or decrease it.
- Advice and information can fit MI only when offered in a person-centered way, typically with permission and without overriding autonomy.
- The 4th edition prefers "fixing reflex" for what older MI writing called the "righting reflex."

## Runtime Flow

```text
user input
  -> safety/scope classifier
  -> motivational language classifier
  -> MI process state identifier
  -> counsellor draft
  -> judge validation
  -> accepted response OR repaired response OR fallback
```

## State

`SessionState` stores recent turns plus three live assessments:

- `SafetyAssessment`: `ok`, `caution`, `urgent`, or `out_of_scope`.
- `LanguageAssessment`: change talk, sustain talk, ambivalence, discord, or neutral.
- `ProcessAssessment`: engaging, focusing, evoking, or planning, with confidence and a `slow_down` flag.

The process identifier can move backward. Discord returns the system to engaging; sustain talk and ambivalence keep it in evoking; planning only appears when there is readiness or commitment language.

## Safety and Scope

Urgent risk bypasses generation and returns a crisis-oriented support message. Medical or medication content is allowed only as reflective support plus referral to a qualified professional. Out-of-scope topics are redirected to smoking cessation.

## Judge Criteria

The judge rejects drafts that:

- give uninvited advice;
- plan before readiness evidence appears;
- ignore sustain talk or discord;
- diagnose, prescribe, or provide medication dosing;
- use shame, confrontation, pressure, or scare tactics;
- miss urgent safety handling.

Rejected drafts get one repair attempt. If repair also fails, a conservative fallback response is used.
