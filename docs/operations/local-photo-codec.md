# Offline photo preparation and Home assets (2026-10-10 LOCAL)

Media owns the bounded photo header/Worker/codec path. Only World Feed and Chat opt
into `user-photo`. Reference, creation and profile inputs keep their prior policy.
The original File is not modified. Each picker owns one Worker, aborts/terminates it
on supersession or unmount, and enforces 30 seconds and at most six encode attempts.

| Boundary | Contract |
|---|---|
| Original user photo | JPEG/PNG/WebP/HEIF/HEIC; 20 MiB |
| Before decoding | Each side 16,384 px; 64,000,000 pixels |
| Attachment copy | JPEG/PNG/WebP; 10 MiB; each side 4,096 px; 16,777,216 pixels |
| Exact `POST /media/assets` JSON body | 14 MiB, including Base64, in both Next and ASGI |
| World/profile file | Existing 5 MiB; crop output independently checked |
| Four World media POST JSON bodies | Existing 8,262,144 bytes |
| Other requests | Existing 1 MiB default and existing narrow exceptions |

The four World paths are `/worlds/{id}/icon`, `/banner`, `/my-profile/media` and
`/world-characters/{actor}/profile/media`. Empty or extra segments and other methods
do not qualify. Authentication, CSRF, scope, revision and streaming byte accounting
stay in their existing owners. The server independently verifies Base64, MIME, final
bytes, decoded geometry/frame count and normalized output.

Structure and dimensions are checked before pixel allocation. Already suitable files
pass through without gratuitous encoding; larger files are proportionally scaled,
retaining JPEG/PNG/WebP when the browser can encode that format. The exact input pixel
cap is 64,000,000, not 64 times 1,024 squared. Browser decoding applies EXIF orientation
once; alpha is preserved. HEIF uses the primary still image and its native alpha flag:
opaque output uses JPEG and alpha output uses PNG. Damaged/animated/unsupported/oversized/timed-out input has distinct
ko/en feedback. No remote conversion service is used. Successful upload alone replaces
the old attachment; failure preserves text and the old attachment. Chat preflight
continues checking the actual uploaded asset and its `allowed`/thread/recognition gate.
Selection/conversion alone does not publish, send messages or call AI.

## Decoder source and rights

- npm `libheif-js` **1.23.5**, pinned in the lockfile; source
  <https://github.com/catdad-experiments/libheif-js/tree/d8ec4bc3bc5bf8055975577bccbbc7e1d7313c2d>.
- Build source
  <https://github.com/catdad-experiments/libheif-emscripten/tree/5c8968a44e9c68ae677e24790d77d001ed7fe7cc>.
- Native libheif 1.23.5:
  <https://github.com/strukturag/libheif/tree/413e2a87e6a70b3eccc3a3adc5801179dd2d9e00>.
  The default HEVC decoder is libde265 1.0.15; build tooling is Emscripten 3.1.61.
  The wrapper uses the shipped native C ABI, not assumed Embind methods.
- The security-limit structure version is checked, then pixel and **512 MiB native
  block/total memory limits** are applied before parsing/decoding. These are codec
  limits, not a 512 MiB bound for the entire browser, Worker or WASM heap. Pixel/time/
  attempt bounds and Worker termination are additional controls. All native pointers,
  handles, bitmaps and canvases are released in success and failure paths.
- The HEIF module loads only for HEIF. Worker/WASM is local in Next and static bundles.
  CSP adds `wasm-unsafe-eval`, not production JavaScript `unsafe-eval`. Static includes
  the local license directory. The app's license screen links notices and source.
- `security/license_policy.json` records the LGPL-3.0 dependency obligations separately
  from Angmoo GPL-3.0-only. Ship original libheif-js/libheif/libde265 license texts and
  build/source links. Preserve the right to inspect, modify and replace/rebuild this
  open-source bundle; do not introduce an asset access restriction.
- Any upgrade requires version/source/license review and both-runtime primary HEIC,
  orientation/alpha/early-limit/abort tests. Pinning is not proof of support for all
  HEIF codecs or all camera files. No actual image AI is involved in these checks.

## Home wordmark source

Only the Home Angmoo wordmark uses Quicksand Bold 700, brand accent `#ff6b6b`, 1.35 rem,
`font-display: swap` and system-stack fallback. Other UI keeps its existing system stack.
Official Google Fonts source is pinned to
<https://github.com/google/fonts/tree/e3b5462bdd8153237ad58a3766d456d89c6a2f48/ofl/quicksand>.
`Quicksand-wght.ttf` SHA-256:
`39c9b64223561f56aaff6062a6f04063c4fc86809ad6768722c06614d977e1cc`.
Copyright 2011 The Quicksand Project Authors, Reserved Font Name Quicksand, SIL OFL 1.1.
Original OFL is preserved beside the font and in `public/licenses/Quicksand-OFL.txt`.
No remote or preinstalled font is required.

The design checker accepts only this exact licensed digest, exact local font-face
and matching original/public notices. Remote/unreviewed fonts still fail. Exact
synthetic photo hashes are separate diagnostic assets, not canonical screenshots.
See [verification record](../verification/creator-studio-copy-media-scheduler-20261010.md).
