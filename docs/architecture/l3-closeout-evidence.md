# L3 integrated clean-clone closeout evidence

Status: **L3 PASS_P1_P4_LOCAL_VERTICAL_LOOP / PR H PASS AND MERGED / L3-ER0 NEXT**

Baseline:

- repository: `angmoo-tree/angmoo`
- PR G merge commit: `480fd2974eb83edb09ace85300b1102f7acf98e5`
- PR H issue: `#93`
- branch: `test/l3-p1-p4-vertical-loop-closeout`
- migration head: `20260819_0082`
- previous L3-safe revision: `20260816_0080`
- local evidence commit: `438b96c2c16e4e46bd4e6c66510c655261a97cd0`
- final PR head: `3d9ecc5157aa0fe0b39a901c8f3f59f222eb492d`
- exact merge commit: `6119129334193b35b8eb737bd79a3c47ce911afe`
- PR state: merged; Issue `#93` closed; remote branch deleted

## Local execution evidence

Executed on Windows from an isolated Compose project named
`angmoo-l3-pr-h-438b96c`:

- representative L3 suites: `67 passed, 1 skipped`
- backend full suite: `1125 passed, 21 skipped`
- frontend: typecheck PASS, lint PASS with one pre-existing warning, production
  build PASS
- Windows launcher smoke: `windows_local_smoke=pass`, launcher PASS, DPAPI PASS
- public secret scan: `807` text files and `4` binary files inspected,
  `findings=0`, `fatal=0`
- source-image clean-clone: six-service full mode PASS, three-service core mode
  PASS, four-service autonomy mode PASS, provider calls `0`
- migration round trip:
  `20260819_0082 -> 20260816_0080 -> 20260819_0082`
- canonical row/ID digest before and after the round trip:
  `0||1|1348052885f848a74d61942f01461bf2|0||2|19f63f8294863b6fae9831970626dbb4`
- port-conflict fixture: automatic port move `0`, unrelated process kill `0`
- fixture cleanup: no `angmoo-l3-pr-h-438b96c_*` volume remains
- canonical development stack: all six services remain healthy and all five
  `angmoo_angmoo_*` canonical volumes remain present

The local results above prove the local technical Gate. Hosted evidence is
recorded separately below. The Local Owner final screen and merge Gates were
subsequently completed.

Hosted evidence:

- PR: [#94](https://github.com/angmoo-tree/angmoo/pull/94), merged as
  `6119129334193b35b8eb737bd79a3c47ce911afe`
- required and advisory Actions: `14/14` PASS
- `local-core-smoke` completed the container supply-chain and clean-clone Gate
  in `6m58s`; this was normal execution, not a stalled job
- an initial documentation-state assertion failed after this evidence document
  advanced from `IN PROGRESS` to `LOCAL TECH PASS`; the assertion was corrected
  without changing product behavior and the rerun passed

After merge, exact `main` images were rebuilt with revision
`6119129334193b35b8eb737bd79a3c47ce911afe` and version
`sha-611912933419`. A second isolated Windows clean-clone named
`angmoo-l3-final-main-6119129` passed the same `0082 -> 0080 -> 0082`
migration round trip, full/core/autonomy modes, repeat-start and persistence
checks, port-conflict classification, and provider-call `0` contract. Its
containers and volumes were removed, while the canonical six-service stack and
five `angmoo_angmoo_*` volumes remained healthy and present.

The same commit was then cloned from the public GitHub HTTPS URL with terminal
prompts and credential helpers disabled. That clean checkout was empty of local
changes and its source images passed the same six/three/four-service,
`0082 -> 0080 -> 0082`, provider-call `0`, and fixture-cleanup contract under
the isolated project `angmoo-l3-final-anon-6119129`.

The PostgreSQL row/count digest, Neo4j World projection digest, and production
typed-query digest are frozen in
[`l3-er-postgres-neo4j-parity-oracle.json`](l3-er-postgres-neo4j-parity-oracle.json).
This is the rollback and parity oracle for L3-ER0 onward; it contains no raw
user content, credential, secret envelope, or absolute user-home path. Release
tagging remains a separate approval.

## Required automated evidence

| Gate | Required evidence |
|---|---|
| Representative loop | P2 3 physical requests and 40 candidates; P3 four-item provider-free plan; P4 atomic continuation; owner write provider 0; Inbox one-time consume |
| Migration | clean fixture `0082 -> 0080 -> 0082`, unchanged World/Character/WorldCharacter/Post ID digest, autonomous backfill mismatch 0 |
| Lifecycle | repeated start idempotent; normal stop/start preserves DB marker and APP_SECRET digest; missed catch-up write 0 |
| Scope | World A/B isolation; Local Owner binding; autonomous-author spoof and cross-World target fail closed |
| Graph outage | PostgreSQL canonical loop remains available while Neo4j projection reports degraded and can replay |
| Privacy | provider endpoint marker 0; raw key, APP_SECRET, encrypted envelope, raw provider payload, absolute user-home path 0 |
| Platforms | backend focused/full; frontend typecheck/lint/build; Windows launcher smoke; six-service clean-clone container Gate; Hosted Actions |

The Local Smoke workflow runs the P1-P4 representative suites, owner-controlled
identity and Inbox suites, architecture contract, and this closeout contract.
The container Gate builds source images in a unique Compose project, creates only
fixture volumes, verifies the migration round trip and lifecycle, and removes the
fixture volumes in `finally`. Canonical `angmoo_*` volumes are outside that
project and must remain untouched.

## Human evidence completed

The Local Owner confirmed PASS in the final user stack for:

1. Device Home -> Creator Studio -> World App -> Feed -> Home navigation.
2. An autonomous P1-P4 sequence and the owner-controlled minimum-participation
   sequence are visible in the same World without cross-World data.
3. Restart preserves the plan, owner profile, manual post/reply, and consumed
   Inbox state without catch-up posts.
4. The manual reply can be observed once on a later allowed beat; a public reply
   is optional and duplicate observation is absent.

The final screen was confirmed after all required Actions passed. PR #94 was
then merged, its remote branch was deleted, exact-main clean-clone evidence was
repeated, and the parity oracle was frozen. L3 is therefore
`PASS_P1_P4_LOCAL_VERTICAL_LOOP`; L3-ER0 is next.
Release tagging remains a separate approval gate.
