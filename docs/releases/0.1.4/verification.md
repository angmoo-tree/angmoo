# Angmoo 0.1.4 prepublication acceptance and limits

Product source **7d0cfabca490261461d4f4b7426ad16e60e4e996** is fixed. The installer, six OCI platform payloads and source-stamped migration tools come from that source. They are not rebuilt when qualification tooling or release records change.

**The four platform acceptance paths below are complete within their recorded scope.** The final exact-installer USER CHECK is complete: the maintainer confirmed installation, launch, home entry and existing-data display, and kept the app open. The physical installed payload is verified as S. Independent running-image identity remains `corroborated`, not fully verified, as explained below. This prepublication record does not itself establish that a tag, registry image or GitHub Release has been published.

## Source and producer binding

| Evidence layer | Source-bound result |
| --- | --- |
| Product review | [PR #418](https://github.com/angmoo-tree/angmoo/pull/418), explicit maintainer Gate on HEAD 504c5c40c977217f83f298d556360c1ee08a8886, normal merge to product source S |
| Main Core CI | [41080463006](https://github.com/angmoo-tree/angmoo/actions/runs/41080463006): 7,768 passed, 309 explicitly skipped, zero failures/errors across 8,077 disjoint reported cases |
| Local Smoke | [41080463020](https://github.com/angmoo-tree/angmoo/actions/runs/41080463020): PASS |
| Security and Governance | [41080462937](https://github.com/angmoo-tree/angmoo/actions/runs/41080462937): PASS; this is the configured policy result, not a claim of zero known advisories |
| Windows producer | [41080462974, attempt 2](https://github.com/angmoo-tree/angmoo/actions/runs/41080462974/attempts/2): full clean-install, official 0.1.3 upgrade and failure-recovery matrix PASS |
| Container producer | [41081578283](https://github.com/angmoo-tree/angmoo/actions/runs/41081578283): native amd64 and ARM64; six original payloads; runtime, search/migration features and configured native/security checks PASS |
| Additional ARM64 qualification tooling | [PR #419](https://github.com/angmoo-tree/angmoo/pull/419), reviewed HEAD 4ed29d9a93535c2664031611cce29e3b44c55c72, normally merged as T 53721a31f2e346d44f4e57866a940b29da5285b4; exact S archives reused, no product rebuild |
| Native Docker ARM64 adapter | [41136047745](https://github.com/angmoo-tree/angmoo/actions/runs/41136047745), T workflow using S production archives: official 0.1.3 synthetic input, controlled store interruption/resume, new write/restart, actual cold restore and old SQLite rollback PASS. Sanitized artifact 13015673691 was downloaded and checked against its API ZIP digest. |

Windows artifact 12994010282 is tied to attempt 2, and Container Candidate artifact 12989882670 is tied to attempt 1. Their original ZIP transport digests, per-payload manifests, SBOMs and provenance were checked. The Windows workflow attestation was verified against S and the designated producer workflow. The EXE is **not Authenticode-signed**.

Final installer SHA-256: `60ae465a1cb01652a6426103d902e1c1089ccc1c5f282023c5d63c5ae027562d`, 311,814,564 bytes. P5 contains all six immutable platform manifest digests.

The first same-source Windows attempt reached successful migration and a new PostgreSQL write, then timed out while stopping the failure-recovery sidecar. One bounded same-source workflow retry passed. The first failure is retained; its precise transient shutdown cause is not established.

The later tooling PR had a separate Windows CI failure: [41109951335 attempt 1](https://github.com/angmoo-tree/angmoo/actions/runs/41109951335/attempts/1) timed out during final silent reinstallation after conversion, new writes/restart, uninstall and retained-data comparison. A single same-head whole-workflow retry passed all three installer cases. Its exact transient cause remains unconfirmed. That CI produced tooling-source binaries; it did not replace the fixed-S release installer or its USER CHECK.

## Platform checks

| Platform | What was exercised | Acceptance |
| --- | --- | --- |
| Docker amd64 on Windows | Distributed migration EXE; automatic source discovery/selection; official 0.1.3 copy conversion; three services; new Unicode value, reread and restart; real cold backup/restore; old SQLite backend rollback | Agent check PASS; native fresh-install/features CI PASS |
| Docker ARM64 on native Linux ARM64 | Fixed-S native fresh-install/features CI plus native end-to-end source-stamped Python migration tool qualification; synthetic official 0.1.3 copy; store interruption/resume; three-service start, new Unicode write/restart, actual cold restore and old SQLite rollback | CI PASS; ARM64 emulation false. This is not macOS-host qualification or a real-AI/search-quality test of that synthetic fixture. |
| Termux/PRoot ARM64 | Actual phone, fresh installation and an actual official 0.1.3 data copy; 181 tables/27,506 rows; new write/restart; 3,037-entry cold archive restored to an empty home with exact hashes, UID/GID and modes, then booted | Agent check PASS with experimental Android limits |
| Windows x64 | Actual NSIS install/update/recovery in isolated hosted Windows matrix, fixed-source bundled PostgreSQL/pgvector and persisted new writes/restarts | CI PASS; maintainer USER CHECK PASS for final EXE installation/startup/home/existing-data display; partial independent running identity kept separate |

Docker source copies and original resources were kept. Local QEMU's failed target services were normally stopped after diagnosis; no timeout bypass, service replacement or resource deletion was used to manufacture a pass. Old backend-only rollback evidence is not an old frontend UI check.

The native ARM64 adapter fixture contained one bootstrapped owner, a Unicode metadata marker and an uploaded file, with no World/character/post/memory/relationship rows. It proves that host's official-format adapter, interruption/resume and storage lifecycle; it does not prove populated-memory migration quality by itself. Populated historical data and recall evidence come from the actual phone and Windows copies plus the shared conversion and native fresh-feature checks, with those evidence layers kept separate.

The personal phone environment was stopped temporarily during isolated qualification and returned to its original source/configuration/launcher with HTTP 200. It was not overwritten by S. Original SQLite files, fallback images and PC backups remain separate from the migrated copies.

The final Windows USER CHECK is bound to the exact installer hash above. The agent observed Device Home ready with five existing Worlds. The physical installed payload and native resources were verified at their actual opened paths. Windows retained the previous `app.__install_staging__` name in the running image mapping; canonical launch paths, PE headers and executable code matched, so the diagnostic helper returned `running_state=corroborated` with exit 2. This is partial independent running evidence, not a full running-identity PASS or an installation failure. The maintainer's direct UI confirmation is recorded as USER CHECK and is not replaced by automated CI. No reinstall, data reset or security-setting change was performed by the agent to reconcile the mapping name.

## Actual AI and memory/search checks

On the migrated and actually restored phone copy, one normal Chat request committed a response; SNS completed two Inbox replies; 20 memories and their snapshots were stored; all three relationship targets completed with `keep` and zero failures. Keeping the relationship perception is a completed review, not an omitted review.

The directed validation sent **14 actual SDK HTTP attempts**, maximum seven within any rolling 60 seconds, minimum interval 5.2017 seconds. The agreed ceiling was 50 total, at most 14 per rolling minute, at least five seconds apart, and at most two transmissions of the same logical request payload. The original model returned one HTTP 503 and one HTTP 504. Under the maintainer's prior authorization, only the test copy used an alternate model for new representative requests; API keys and personal settings were preserved.

Keyword and exact-vector axes returned results within the correct character/owner scope. Existing-vector self-distance was zero and wrong-owner retrieval returned zero items. An actual Chat response used an older migrated memory. A later natural-language query returned a related newly saved episode instead of the single old memory ID required by a stricter harness expectation; that raw `NEEDS_REVIEW` result is retained. Its semantic relevance was assessed separately and was not relabelled as a passing exact-ID test.

Two Inbox recall packets were inspected: one was clearly related and one was a broader, weaker match. Feed and Routine did not request memory search in that run. This is representative functional and relevance evidence, not a general search precision/recall benchmark. Legacy memories lacking full historical source material retain `partial`/`degraded` source-packet status; missing originals were not fabricated during migration.

Queue controls were exercised using labelled synthetic durable failure states and normal owner APIs on the real PostgreSQL copy: pending cancellation, remaining/storage resume, close without retry, retained history, preserved completed work and no revival by a later normal save. Synthetic fault cases are distinguished from the actual AI run.

## Phone resources and limits

The initial 600-second idle observation with only ten seconds of warmup recorded **14.56% of one CPU core** and failed the strict 10% limit. The first minute contained startup work. A separate measurement was declared with a fixed 120-second warmup, retaining the same images, normal worker topology and strict threshold.

The second 600-second steady-idle result was **9.6795% of one core**, or **1.2100% across eight cores**. Whole-process-tree PSS averaged 494,981,775 bytes (472.05 MiB), maximum 499,770,368 bytes (476.62 MiB); SwapPSS was zero. Services retained their process identities and scheduler/projector readiness. This measures the entire Angmoo tree, not PostgreSQL alone.

The phone was awake and USB-powered. No 30-minute or 60-minute load test was run. These checks do not certify Doze survival, all Android devices, a minimum-RAM device, unlimited characters or sustained maximum workload.

## Scope retained for later work

- Direct migration supports official 0.1.3/schema 41 to 0.1.4/PostgreSQL schema 5. Earlier private PostgreSQL versions are not an official migration input.
- macOS-host migration qualification/support is deferred. ARM64 image availability does not prove a macOS migration result.
- Previously observed Windows serialization one event and two unfinished SNS records received diagnosis/handoff only. This release does not claim those historical observations were fixed or replayed.
- Chat-image layout, new-World language defaults and startup memory-inventory cost are separate follow-up work.
- Three existing medium-severity glib dependency alerts remain visible in repository dependency reports. Passing configured release scans does not mean every advisory has disappeared.
- S is the product source; T is separately reviewed qualification-only tooling at 53721a31f2e346d44f4e57866a940b29da5285b4; R is the later reviewed main commit containing this release record, pinned as `p5.review_ref` in the release manifest. S-to-T changes exactly nine CI/policy/current-inventory files; T-to-R changes only this release's records. Runtime, frontend, desktop, launchers, production Dockerfiles/dependencies, original migration tool and bundled guides remain unchanged from S.

Anonymous public asset hashes/downloads, registry index/platform/config/layer access and preservation of earlier releases are a separate postpublication evidence layer. They are not inferred from the prepublication acceptance above. The release manifest pins the reviewed record, immutable source and artifact hashes.
