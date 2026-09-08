# Roadmap

Implement white-box synthesis first. Add refinements through use.

## Core contract

- [X] Accept a passage plan, ordered arguments, fragments, and constraints.
- [X] Execute COPY, INFLECT, NORMALISE, ORDER, and DELETE.
- [X] Trace output wording to exact source spans and recorded edits.
- [X] Return typed gaps and provenance records for human review.
- [X] Mark unchecked transformations Unverified and block selection.

## Meaning and causality

- [X] Record optional agent diagnostics with exact basis spans.
- [ ] Identify causal gaps and contradictions with source meaning.
- [ ] Evaluate meaning, scope, modality, and causal direction on reviewed cases.

## Refine and extend

- [ ] Verify more inflections and spelling normalisations.
- [ ] Improve source-wording measurement and diagnostics.
- [ ] Add source ingestion, resumable runs, and immutable source versions as needed.
