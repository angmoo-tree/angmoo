# L3 integrated clean-clone closeout evidence

Status: **PR H IN PROGRESS / USER MERGE GATE NOT REACHED**

Baseline:

- repository: `angmoo-tree/angmoo`
- PR G merge commit: `480fd2974eb83edb09ace85300b1102f7acf98e5`
- PR H issue: `#93`
- branch: `test/l3-p1-p4-vertical-loop-closeout`
- migration head: `20260819_0082`
- previous L3-safe revision: `20260816_0080`

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

## Human evidence still required

Before L3 PASS, the Local Owner must confirm in one clean-clone stack:

1. Device Home -> Creator Studio -> World App -> Feed -> Home navigation.
2. An autonomous P1-P4 sequence and the owner-controlled minimum-participation
   sequence are visible in the same World without cross-World data.
3. Restart preserves the plan, owner profile, manual post/reply, and consumed
   Inbox state without catch-up posts.
4. The manual reply can be observed once on a later allowed beat; a public reply
   is optional and duplicate observation is absent.

Only after the Draft PR passes all required Actions, the user confirms the final
screen, and the PR is merged may the plan record
`L3 PASS_P1_P4_LOCAL_VERTICAL_LOOP`. Release tagging remains a separate approval
gate.
