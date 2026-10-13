# Independently authored ComfyUI examples

`scripts/diagnostics/author_comfy_image_samples.py` owns these example graphs.
Its default `--format=config` preserves the historical Angmoo settings examples.
`--format=api_json` emits only the API graph, in deterministic UTF-8 with LF.
No third-party workflow JSON or custom-node code was copied into these assets.

Text uses ComfyUI core checkpoint, CLIP, latent, sampler, VAE and SaveImage nodes.
Reference uses the optional `ETN_LoadImageBase64` node from
[Acly/comfyui-tooling-nodes](https://github.com/Acly/comfyui-tooling-nodes).
The inspected `nodes.py` revision is `b3ae4aa2d98f6ac4284ddbe261e3559c94bd652b`,
SHA-256 `296330305db27e8b457c7b26856dff2fb5fcdf232612a1a7b3ca3c2a85124474`.
Its `image` STRING input accepts bare Base64 and its IMAGE output is slot 0.
The example connects that IMAGE to ImageScale and VAEEncode, and also supplies
positive and negative text conditioning. Angmoo neither installs that node nor
guarantees the user's node/model versions or GPU quality.

Model names must be actual installed checkpoint names. No fabricated default
model or VAE is supplied. The source graphs keep placeholders; generated PNG
Base64 and Partner credentials belong only to send-time preparation, never to
the example, stored graph, download, diagnostic or execution snapshot.

See `docs/verification/comfy-security-20261012.md` for scoped evidence and the
separate limits of synthetic transport, installed app and real GPU verification.
