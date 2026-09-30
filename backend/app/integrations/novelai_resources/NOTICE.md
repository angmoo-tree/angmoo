# T5 tokenizer resource

`t5.spiece.model` is the SentencePiece tokenizer (not image-model weights) from
Google's `google-t5/t5-small` repository, commit
`df1b051c49625cf57a3d0d8d3863ed4d13564fe4`.

Source: https://huggingface.co/google-t5/t5-small/blob/df1b051c49625cf57a3d0d8d3863ed4d13564fe4/spiece.model

The upstream model card declares Apache-2.0. License:
https://www.apache.org/licenses/LICENSE-2.0

SHA-256: `d60acb128cf7b7f2536e8f38a5b18a05535c9e14c7a355904270e15b0945ea86`.

Local validation uses the standard T5 SentencePiece vocabulary conservatively.
NovelAI's server-side weighting/parser and exact token accounting still require
the deferred real-provider validation. No SillyTavern implementation or NovelAI
frontend implementation is included.

Exact V4.5 Full server equivalence is UNVERIFIED. Since 2026-10-01 the pinned
local tokenizer is used for conservative preflight, not an unconditional
generation block. Independently written `v4.5-t5-weight-spans-v1` recognizes
the documented `{}`, `[]` and numerical `::` control operators, encodes the
delimited text spans separately and reserves one EOS token. The raw positive
and negative prompts are still sent unchanged. Unknown pieces or a local count above 512 are rejected
without truncation, translation, a generation submission or an admission-time
attempt reservation. This may reject some prompts the server would accept;
it is not a proof of exact server token accounting.

Resource integrity, account/cost mode, quotas and provider error handling remain
mandatory. A normal prompt can reach the real API while `exact_verified` stays
false. Successful subscription checks or generation do not certify the exact
tokenizer/parser or 512-token boundary. No switch can claim exact verification.

Public sources checked 2026-09-30:
- https://docs.novelai.net/en/image/models/ documents approximately 512 T5
  tokens over base and character prompts; it does not pin this resource hash.
- https://docs.novelai.net/en/image/strengthening-weakening/ describes weighting
  syntax, without an exact server token-accounting specification.
- https://github.com/NovelAI/t5/blob/main/docs/tokenizers.md documents divergent
  tokenization around special tokens and normalization. It does not establish
  the exact deployed V4.5 parser/tokenizer combination.

Production-path tests use synthetic HTTP responses with the real local tokenizer,
without a synthetic exactness override. They cover wire fields, cost/account
checks, admission and attachment, but do not certify real-provider behavior.
