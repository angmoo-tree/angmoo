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

Exact V4.5 Full prompt validation is UNVERIFIED. The approximate local check is
not authorization to submit a request. Production settings admission, queued-job
preparation and the NovelAI adapter block generation with
`novelai_prompt_validation_unverified` until a versioned exact model validation
resource/parser and its independent fixtures are established. There is no
user-controlled or environment override for this gate.

Public sources checked 2026-09-30:
- https://docs.novelai.net/en/image/models/ documents approximately 512 T5
  tokens over base and character prompts; it does not pin this resource hash.
- https://docs.novelai.net/en/image/strengthening-weakening/ describes weighting
  syntax, without an exact server token-accounting specification.
- https://github.com/NovelAI/t5/blob/main/docs/tokenizers.md documents divergent
  tokenization around special tokens and normalization. It does not establish
  the exact deployed V4.5 parser/tokenizer combination.

Serializer tests use an explicitly injected synthetic verified capability to
test wire fields in isolation. They do not certify production exactness.
