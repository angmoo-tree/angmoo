# L3.5 World Package v1 format and security contract

Status: **FROZEN FOR PR A REVIEW**

Owner: `app.domains.world_packages`

Public Issue: [#150](https://github.com/angmoo-tree/angmoo/issues/150)

This document freezes the data-only interchange contract before any upload,
archive extraction, database migration, or UI behavior is implemented. A World
Package is an initial, portable World seed. It is not a database backup, a
running World snapshot, an Angmoo Nest publication, or proof of authorship.

## Product boundary

One `.angmoo-world` file contains exactly one World and zero or more autonomous
character templates that are initially placed in that World. Import creates new
local identities; it never transfers source database IDs or owner bindings.

Export and import are deterministic code paths and make **zero provider calls**.
Creator text is untrusted data. It must never become executable code, HTML, a
system instruction, a credential source, or a reason to access the network.

## Container contract

- Extension: `.angmoo-world`
- Media type: `application/vnd.angmoo.world+zip`
- Container: ZIP, data-only
- Text encoding: UTF-8 without BOM
- Hash algorithm: SHA-256
- Format: `angmoo-world-package`
- Format version: `1`
- Schema version: `world-package-v1`

The root layout is closed:

```text
manifest.json
content/world.json
content/characters.json
content/world-characters.json
assets/index.json
assets/sha256-<64 lowercase hex>.webp   # zero or more
LICENSE.txt                             # only when referenced by LicenseRef
```

Unknown archive paths fail closed. Future fields may only appear in an explicit
JSON `extensions` namespace. An importer may ignore an unknown optional
extension, but must reject an unknown required extension.

The checked-in schemas are generated from the Pydantic contract:

```text
backend/app/domains/world_packages/schemas/v1/
├─ manifest.schema.json
├─ world.schema.json
├─ characters.schema.json
├─ world-characters.schema.json
└─ assets-index.schema.json
```

Run the deterministic schema guard with:

```powershell
backend\.venv\Scripts\python.exe scripts\ci\generate_world_package_schemas.py --check
```

## Included portable seed

### World definition

- name and tagline
- setting and daily-life descriptions
- genre and tone tags
- timezone and language
- additional generation guidance
- enabled places, roles, daypart profiles, allow/forbid rules, and glossary
- banner alt text and an optional managed banner asset reference
- source World contract version and source definition hash

### Autonomous Character template

- package-local character reference
- display name and handle hint
- one-liner, personality, speech style, worldview, and persona summary
- topic preferences and safety rules
- optional managed avatar and banner asset references

### WorldCharacter seed

- package-local character and role references
- portable role description, background, and access scope

On import, every template receives a new local UUID7. Autonomous characters are
owned by the current local installation owner only as a new local DB fact. Each
WorldCharacter starts pending, autonomous activity disabled, and with the
current Angmoo runtime defaults. These runtime values do not come from the
package.

## Excluded data

The following must not appear in v1:

- source World, Character, WorldCharacter, membership, or owner IDs
- owner-controlled Character/profile or local owner binding
- session, cookie, machine path, host name, or installation identity
- API key plaintext, ciphertext, metadata, or `APP_SECRET`
- row versions, DB timestamps, idempotency keys, archive state, or active cursors
- posts, replies, likes, reposts, follows, notifications, or Inbox state
- `SocialEvent`, relationship evidence/state/change, or graph outbox
- chats, messages, CharacterState, memory, mood, or private summaries
- P2 profile/candidates/provider attempts, P3 plans/reservations/cursors, or P4
  episodes/beats/runs/publication state
- scheduler leases, projector cursors/replays, logs, diagnostics, crash reports,
  SQLite/FTS5/LadybugDB files, or query results

Initial relationships are excluded because current Angmoo relationships are
derived from successful social events and evidence. Importing them as seed data
would misrepresent runtime history. A future initial-relationship feature needs
its own canonical domain model and versioned schema.

## Managed media

Only media already managed under Angmoo World/Character media ownership may be
exported. External HTTP(S) URLs are not downloaded. They become a preview
warning and a null reference.

v1 assets are static WebP images only. A later archive adapter must verify magic
and MIME, decode with bounded dimensions/pixels, remove metadata, re-encode to a
normalized WebP, and recompute the digest before promotion. SVG, HTML, animated
images, fonts, executables, scripts, nested archives, and polyglots are rejected.

## Manifest and integrity

`manifest.json` contains package identity/version, UTC creation time, producer,
reader compatibility, license, the canonical entry index, content digest, and
required/optional extensions. It does not index itself.

Each indexed entry records:

- canonical package-local path
- SHA-256 digest
- canonical byte length
- media type

`content_digest` is SHA-256 over the canonical JSON form of the entry index,
sorted by path. The entry index includes `path`, `sha256`, `bytes`, and
`media_type` only.

Canonical JSON rules are:

- Unicode strings and object keys normalized to NFC
- key sort fixed
- compact separators fixed
- UTF-8 without BOM
- NaN and Infinity forbidden
- non-string object keys forbidden
- object keys colliding after NFC normalization forbidden
- package-local paths ASCII-only

Reproducible archive generation in a later PR must additionally fix ZIP entry
order, timestamp, permission bits, compression algorithm/level, and must omit
source filesystem timestamps.

## Integrity is not author identity

SHA-256 proves that content still matches the manifest; it does not prove who
created the package. v1 exposes only:

- `locally_exported`: this installation has a successful export registry row
  with the same digest.
- `checksum_verified_unsigned`: checksums match, but author identity is not
  cryptographically verified.

The product must not say `trusted_author` or “signed World Package” for v1.
Creator Studio copy should say “integrity-verified World Package” when the
checksum contract has actually passed.

## License boundary

The manifest contains a bounded license expression, attribution, optional
source URL, and optional `LICENSE.txt` reference. A `LicenseRef-*` expression
requires `LICENSE.txt`. Malformed/unknown license data fails closed until the
later import preview can present a safe decision. The application GPL license
does not automatically license user-created package content.

## Frozen resource limits

| Resource | v1 maximum |
|---|---:|
| compressed package | 128 MiB |
| total uncompressed data | 256 MiB |
| archive entries | 256 |
| manifest | 256 KiB |
| each JSON entry | 2 MiB |
| autonomous characters | 50 |
| image assets | 100 |
| each image | 5 MiB |
| decoded dimension | 4096 px per side |
| total decoded pixels | 200 megapixels |
| entry and total compression ratio | 100:1 |
| path depth | 5 segments |
| path UTF-8 length | 240 bytes |

Limits may be reduced after benchmarks. Increasing a frozen limit requires a
separate security review.

## Archive rejection policy

The parser and archive adapter must reject:

- absolute, drive-letter, UNC, colon, backslash, empty-segment, dot, or `..` paths
- NUL/control characters and Windows device names
- non-ASCII or non-NFC package-local paths
- duplicate, Windows-casefold, or Unicode-NFC/casefold collisions
- symlink, hardlink, device, directory, or encrypted entries
- excessive count, size, depth, decoded pixels, or compression ratio
- unknown/missing root entries or manifest/index disagreement
- missing entries, size/digest mismatch, trailing polyglot content
- nested archives, executables, scripts, HTML, SVG, fonts, and unsupported media

PR A validates pure archive metadata only. It does not read or write user files.
The streaming ZIP adapter, MIME decoder, staging ACL, and trailing-content checks
belong to later PRs and must enforce this same policy.

## Safe error and observability contract

The stable reason codes are the values of `WorldPackageReasonCode`, including
owner/source, upload/archive/path/limit, format/compatibility, integrity/license,
asset/reference/duplicate, stage/preview, and commit failures.

API details and ordinary logs must not expose raw exceptions, absolute paths,
archive entry names, World/persona text, license text, owner IDs, package bytes,
credentials, or secrets. Later observability may record operation ID, package
ID/version, digest prefix, state, counts, duration, byte counts, and safe reason
code.

## Domain-first ownership

`app.domains.world_packages.public` is the only supported cross-domain import.
The domain/application layers must not import FastAPI, SQLAlchemy, provider SDKs,
runtime implementations, another domain's infrastructure, or filesystem path
selection. Frontend and Tauri never open SQLite or LadybugDB directly.

PR A intentionally contains no route, DB table, archive/filesystem adapter,
provider call, or frontend behavior. PR B will introduce caller-owned UoW and
portable seed ports; subsequent PRs will add export, staged import, UI/native
file dialogs, and clean-clone closeout behind this frozen contract.
