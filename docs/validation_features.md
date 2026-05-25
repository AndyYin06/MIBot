# Validation Feature Draft

## Local MITI Micro-Metrics

Purpose: supplement LLM global MITI ratings with observable transcript counts that can catch technical drift.

Implementation:

- Count counselor reflections and questions to estimate reflection-to-question balance.
- Estimate complex reflection share using transparent markers such as double-sided reflections and inferred meaning.
- Track average counselor turn length to catch verbosity.
- Detect advice or direction without nearby permission.
- Surface concerns in `/miti` output alongside the LLM-generated fidelity report.

## Behavioral Drift Signal

Purpose: address validation findings that live, longer conversations can degrade through verbosity, style drift, and question-heavy counseling.

Implementation:

- Flag sessions when later counselor turns become much longer than earlier turns.
- Flag question-heavy transcripts where questions substantially outnumber reflections.
- Feed the same local drift concern into judge repair instructions for generated responses.

## Crisis Protocol Validator

Purpose: validate crisis responses against concrete safety behaviors rather than only detecting crisis keywords.

Implementation:

- Check for risk acknowledgment, empathy, help-seeking, specific resources, and continued engagement.
- Let the judge reject incomplete crisis responses even if a model judge accepts them.
- Keep urgent-risk classification outside the generation path.

## Authority-Bypass Misuse Detection

Purpose: cover adversarial prompts that frame harmful persuasion as research, clinical work, teaching, or other authority contexts.

Implementation:

- Cover authority-context misuse in the safety/scope classifier prompt rather than with case-specific regexes.
- Preserve the out-of-scope response path that redirects to health-supporting, autonomy-respecting use when the classifier returns persuasive misuse.
