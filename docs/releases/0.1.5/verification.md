# Angmoo 0.1.5 verification

Checked on 2026-11-15. This record covers product source **`bd932365266aa6d2e0b8813004ebb303b2ae90cc`**, merged through [PR #431](https://github.com/angmoo-tree/angmoo/pull/431). It does not reuse the earlier work-branch test result as final-source acceptance.

The update baseline is official 0.1.4 (`7d0cfabca490261461d4f4b7426ad16e60e4e996`). Both releases use PostgreSQL schema 5; this is a PostgreSQL update, not another SQLite migration.

## CI and original artifacts

| Main workflow | Run | Attempt | Result |
| --- | --- | --- | --- |
| `ci.yml` | [43678625987](https://github.com/angmoo-tree/angmoo/actions/runs/43678625987) | 1 | PASS |
| `local-smoke.yml` | [43678625968](https://github.com/angmoo-tree/angmoo/actions/runs/43678625968) | 1 | PASS |
| `security.yml` | [43678625940](https://github.com/angmoo-tree/angmoo/actions/runs/43678625940) | 1 | PASS |

- [Container Candidate](https://github.com/angmoo-tree/angmoo/actions/runs/43679128266), attempt 1, artifact `14147598737`: six OCI payloads, runtime/native checks and security reports passed.
- Candidate ZIP digest: `sha256:6062bddda38e4c5aa762bdf6490ff50a0bd4babeac93396fee3fe5937e08563f`.
- [Common assets](https://github.com/angmoo-tree/angmoo/actions/runs/43678693053), attempt 1, artifact `14146898906`; digest `sha256:347adb8ae964fa14a31e1ddee1f5d1d3b2e106c3e3e34642a33fc5b305606f75`.
- Tested source-packaged Termux tools SHA-256: `694a2899511295e618a2c1fcdad79631091a25376da230876c7ec4f0e5f63d04`. Publication must reproduce these same tool bytes.

| Payload | Platform manifest digest |
| --- | --- |
| backend/linux/amd64 | `sha256:fa824b80a8a4eef1ad5e313882a2871a94a886277e61ed1d48d85a729d8b47b2` |
| frontend/linux/amd64 | `sha256:eb26c3ff428a19190be9a98e2a92309936fbba6162dbe5a398f9263140fa8183` |
| postgres/linux/amd64 | `sha256:d60709e21f1ea7d38cc4130fe4e0418121c83f7075344ebdf2aa312be45364f1` |
| backend/linux/arm64 | `sha256:7b7f1832dc4f6080dea95b22b7db1560160dabc4113327eb660ca90b5db4176a` |
| frontend/linux/arm64 | `sha256:d833eb1ee273ed127caa02f7623261700470ccf72f7168adde98e7c8ee1a6bd8` |
| postgres/linux/arm64 | `sha256:1a1f41b7e08f1abbe827f4b2d70c1fbde98a5e31116e6513270719937d7c0936` |

The first candidate dispatch was rejected at startup by the repository's action allowlist. The signed upstream commits for the two already-reviewed Docker action pins were verified and those exact SHAs were added. The selected-action policy and full-SHA pin requirement remained enabled. The successful run above is the only candidate used here; no failed run is relabeled as passed.

## Native Docker qualification

[PostgreSQL Update Qualification](https://github.com/angmoo-tree/angmoo/actions/runs/43680480514) ran on `ubuntu-24.04` and `ubuntu-24.04-arm`, using the exact artifact above. ARM64 was native, without PC QEMU/binfmt emulation.

Each platform passed: empty installation, official 0.1.4 fixture update, existing business data and references, new Unicode value, restart, controlled backend `SIGKILL` recovery, and cold backup restored into new volumes with exact file hashes and permissions. The fixture includes a user, World, two World characters, a post, a message thread/message, memory and relationship state. All test services were stopped. No private data or provider credentials entered hosted CI, and no external AI was called there.

| Platform | Receipt artifact | Artifact digest |
| --- | --- | --- |
| docker-amd64 | `14147914524` | `sha256:1eca12bcd4cebdba5acc45d04e521a9c7500aa134f76953395a40034dd4f47b1` |
| docker-arm64 | `14148581155` | `sha256:607e3fea90d26132654a90f1181002fec922bf4a8d1c4ea100bfb9b63dd704a4` |

Same-source candidate runtime/native feature checks supplement the update fixture. A separate local Docker amd64 installation reached ready health and the home screen in normal mode with scheduler/projector workers. Isolated Playwright Chromium observed no page errors or HTTP failures. This browser observation is distinct from the CI HTTP check.

## Termux ARM64

A physical Samsung Galaxy A52s ran the three ARM64 payloads through Termux/PRoot. The existing selected 0.1.4 installation stayed stopped and unchanged. Tests used explicit separate homes, ports and copied data; the global command and selected home were not changed.

- The updated copy retained identical fingerprints in **201 tables**. Four PostgreSQL search projection tables changed as derived indexes were rebuilt; no business table was dropped or changed by the update.
- The existing copy contained **540 memories, 18 relationship states and 576 posts**. Encrypted settings were preserved, and the actual provider test exercised the copied credentials without exposing them.
- Shipped keyword search returned three existing documents. Exact-vector queries returned three existing vectors; foreign-owner queries returned zero results. These checks used stored vectors and did not call an embedding provider.
- A new Unicode value survived restart, a controlled backend failure and actual cold restore. The serving role continued to reject DDL.
- A separate empty home initialized PostgreSQL and reached its ready home screen.
- Cold backup/restore checked **46372 entries** by file digest, permissions and owner. The restore recycled only this run's disposable copy after verifying the archive; original data and PC backups were preserved.
- Browser checks covered the home, existing World feed, Chat, memory, relationships and settings. These used PC Playwright Chromium over USB forwarding to the real phone server, not physical Android Chrome. The first unauthenticated `/auth/me` returned 401, followed by successful session issuance and an authenticated `/auth/me` 200; the harness verifies that normal bootstrap explicitly.
- Immediately after restore, a search returned `MemoryRecallPreparing` during startup projection work. The unchanged search passed after preparation completed. Its first result is retained separately, not relabeled as a passed query.

## Real AI

The final-source test used one isolated phone copy with unattended activities and image generation disabled. It called the shipped owner APIs in-process; the normal launcher and HTTP/browser startup were checked separately. Provider replies were real, with no fake response substitution. No new model or account was selected for this test.

| Case | Observed result |
| --- | --- |
| Chat | `{"committed_requests": 2, "retrieved_memory_evidence": [1, 2], "new_fact_in_retrieved_packet_and_answer": true}` |
| Memory storage | `{"completed_runs": 2, "new_memories": 17, "failed": 0}` |
| Embedding | `{"state": "ready", "stored_vectors": 551, "model": "gemini-embedding-2"}` |
| SNS | `{"completed_runs": 1, "new_posts": 1}` |
| Relationship review | `{"target_count": 3, "completed_count": 3, "changed_count": 0, "kept_count": 3, "failed_count": 0}` |
| Before idle | `{"active_vector_items": 0, "additional_calls_to_check_settlement": 0}` |

Actual transmissions: **20 / 50**; maximum rolling 60 seconds: **9 / 14**; minimum interval: **5.202 seconds**. Counts include model lookup, token counting, embedding and retries. Earlier work-branch calls and budgets remain separate.

One Google HTTP 503 response was followed by a successful response; the Chat request committed. Both Chat requests reported `degraded` / `canonical_unavailable` while returning memory evidence. Their FTS and vector axes were ready, with no RRF candidates excluded. Persisted packets show verified historical snapshots and zero missing/changed/unavailable sources; the existing context-character budget omitted some source units, so the fused result was partial. The recalled new test fact appeared in both the retrieved packet and final answer. This confirms bounded retrieval and delivery, not complete context delivery or general ranking accuracy. Four pre-existing source-unavailable vector items remained scheduled; no pending/running/retry vector work remained before idle. An additional state-only reconciliation repeated no successful AI scenario and made no new provider transmission.

## Normal idle observation

The first complete observation followed a fixed 120-second startup warmup. It averaged **17.469%** of one core and **failed** the default 10% gate. Its first minute averaged 78.06%; the following nine minutes averaged approximately 10.74%. That first receipt and its 61 samples are retained unchanged. The short attribution check after it identified CPU in the backend, PostgreSQL and their PRoot processes; it did not establish the precise cause of the earlier high-CPU interval.

A second, predeclared **600.03-second** observation measured the already-running services without a restart or worker/configuration changes. CPU averaged **10.746%** of one core; average resident PSS was **118.3 MiB**, with **265.7 MiB SwapPss** (average RSS **196.5 MiB**). These are separate resident/swapped memory measures, not a total-RAM or battery improvement claim. Validation mode remained off; service identities and health remained valid. The maintainer explicitly accepted idle CPU up to 11% for this source on 2026-11-15. The acceptance result is **`ACCEPTED_EXCEPTION`**; it does not relabel an above-10% measurement as passing the default gate. The release-tool exception is bound to this version, source and approval identifier and cannot accept the first 17.47% result or another candidate.

Before both measurements, an earlier warmup was cancelled before any CPU samples were collected to confirm that pending projection work had settled. That reconciliation made no additional provider calls. No process was removed or worker disabled to reduce the observed CPU.

This is a 600-second idle observation, not a load, battery or long-session endurance test.

## Scope and limitations

- Android remains **experimental-not-certified**. One phone does not establish every Android vendor/version, Doze or background-process policy.
- No PC ARM64 emulation, 30/60-minute load test, macOS-host test or new Windows native installer qualification was performed.
- Native Windows installer distribution/support ends at 0.1.5. Existing code, manual workflows and historical installers remain. No Windows-native-to-Docker data migration tool is supplied.
- Representative AI and search checks do not guarantee every model, prompt or semantic ranking. Private logs/data are retained locally and are not release assets.
- Public-download/user-path verification after publication is assigned to the maintainer separately. It is not represented as completed by these candidate tests.

## Source and artifact integrity

The release tag points to the product source above. These release notes and acceptance records are reviewed separately on main. The review also contains the source-bound idle-CPU acceptance rule and its tests for the release publisher. Product images, launcher and bundled guides remain fixed at the qualified source and are not rebuilt for this release-tool change. The publisher verifies the six candidate payloads, three multi-platform indexes, producer identities, P5 record and staged file hashes before publishing.

Use the published `release-manifest.json` and `RELEASE-SHA256SUMS` to compare downloaded assets. The manifest binds platform/config digests, producer runs, source and the reviewed P5 report. GitHub provenance attestations and the SBOM/security reports provide additional build evidence. A checksum from the same download location is an integrity check, not an independent security guarantee or proof that software has no defects.

Source: [fixed product commit](https://github.com/angmoo-tree/angmoo/tree/bd932365266aa6d2e0b8813004ebb303b2ae90cc). Historical baseline: [0.1.4](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.4). The official 0.1.5 tag and Release are created only after this review.

The following digests bind private detailed receipts to this public summary. They do not make personal data or credentials public.

| Receipt | SHA-256 |
| --- | --- |
| `phone-release-qualification.json` | `4c6f7659fe1e5c6f8d010757c1604951f88e4a65069aad40ccae27d515245c6b` |
| `phone-real-ai.json` | `0cfa268e6017a0131fffa57a25d623368490ebf47092ece28a06e70d42e95ed0` |
| `phone-idle-600.json` | `34ec24a07bc0d91a2d3e8fd9f3bcde023c4e14f74f7b2e528605fe28471407b7` |
| `phone-idle-stable-600.json` | `2d909317246a61e05f8f89e66d503a4c9b5b3db7eb404a09ce7d9e2386b76daf` |
| `idle-cpu-user-approval.json` | `4f4a2888a6c2ac9eecb3e27df45dbe23c1c46ca936fcf4931fe794ddbca279f2` |
| `phone-final-backup-restore.json` | `294c7349b7cdfdd2005cec28636cbfd1b91bfe4bb8361f624fd71f359a718cb8` |
| `native-qualification.json` | `8fde7113eac4d0e248f0df20714212aa526295e7f3c93ab20562224480ac2fd5` |
| `final-preservation.json` | `3516cdca8a7b07129012b18843e0a3df6a23ddc7fa69f920814dc67933ce2953` |
