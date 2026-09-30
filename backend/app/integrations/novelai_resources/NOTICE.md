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
