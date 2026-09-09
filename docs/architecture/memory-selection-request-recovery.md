# Memory selection request recovery — PR #321

Date: 2026-09-09. Same branch/Issue #319/Draft PR #321. USER CHECK and merge remain pending.

## Behavior and ownership

The Memory integration removes only `decisions.maxItems` from its freshly built
Gemini transport schema. The domain schema and parser still require at most 32
sources, exactly one decision for every candidate, matching evidence and subjective
references, 1–120-character retained summaries and atomic storage. No schema
fallback or free-text response path is introduced.

Real medium-thinking validation exposed a second ambiguity: the input carried
subjective text but did not explicitly supply the reference ID expected by the
parser. Some responses copied the text into `subjective_context_refs`. Inputs now
include the permitted `subjective_context_ref`, and the prompt explains ID versus
text. The invalid responses remain rejected rather than repaired or stored.

The Gemini boundary classifies typed SDK HTTP errors and timeout/network exceptions
without retaining provider messages. Memory maps those safe categories to its own
codes. 400/401/403/404 and unknown failures terminate the attempt; 429, supported
5xx, timeout and network failures use the existing durable backoff with at most
three attempts. Each Memory request sets SDK attempts to one. Other callers retain
SDK defaults, and Chat/autonomous-activity output caps do not change.

Legacy `provider_failed` history is preserved and explicit retry can regroup its
unprocessed candidates. Successful-completion timestamps already exclude failed
jobs. Existing UI polling refreshes saved memories on a successful completion.
The Memory feature owns recovery copy; Next and static/Tauri share it. This is
LOCAL recovery behavior with existing ADAPTED presentation; no new hosted assets,
routes, colors, dependencies, schema migrations or sibling source trees.

## Validation evidence

- Focused backend/provider suite: 108 passed before the explicit-ref addition;
  final focused request/batch suite: 32 passed, including that addition.
- Architecture, frontend boundaries, design and regenerated Memory inventory pass.
- Frontend lint/typecheck, Next production build and static export pass.
- Next and static Memory browser tests each pass, including request-rejection copy,
  retry acceptance, terminal completion, disappearance of the old failure and
  existing owner controls/narrow layout.
- Full backend suite and final-HEAD hosted CI are tracked separately in the PR;
  earlier HEAD CI is not reused as current evidence.

### Real provider checks (synthetic data only)

Every final matrix response used one generateContent call, the selected thinking
level and Memory's unchanged 65,536-token ceiling, ended STOP and passed the strict
parser. The matrix includes 10 candidates, 32 candidates and reversed-order 32.

| Profile | 10 | 32 | Reversed 32 |
|---|---|---|---|
| Gemini 3.5 Flash-Lite high | PASS | PASS | PASS |
| Gemini 3.5 Flash-Lite medium | PASS | PASS | PASS |
| Gemini 3.1 Flash-Lite high | PASS | PASS | PASS |
| Gemini 3.1 Flash-Lite medium | PASS | PASS, quality distinction below | PASS, quality distinction below |

The first synthetic corpus deliberately used near-identical commitments differing
primarily in training-plan numbers. 3.1 medium retained one and skipped the rest as
redundant in both 32-candidate cases, diverging from the predeclared expectation.
Those mismatches are preserved, not relabeled as expectation matches. Two additional
3.1-medium 32-candidate cases used 16 genuinely different commitments/preferences
and 16 mundane events in forward/reverse order; both matched every expected
retain/skip judgment. This demonstrates transport/validation compatibility, not
universal recall quality or guaranteed retention of every source.

Before the final prompt, 7 synthetic calls produced 5 valid responses and 2
parser failures. The first failure's response was not captured; the second
demonstrated subjective text in the reference array. Final validation used 12
matrix calls plus 2 distinct-corpus calls: **21 generation calls overall**. No
user candidate was retried or consumed for these checks. Credentials were resolved
inside a temporary container with the contributor volume mounted read-only; keys
and actual source text were not copied into reports.

Parsed real decisions are replayed through the real batch write service against
separate in-memory SQLite fixtures, checking item/decision counts and a second
queue invocation producing no duplicate items. Storage replay is independent of
semantic quality and does not upgrade the two expectation mismatches to PASS.

User verification remains: retry actual failed candidates, inspect retained
memories/evidence, check scheduling/full-app shutdown, and test the new installer.
The agent does not install the app, mark USER CHECK passed, undraft or merge.
