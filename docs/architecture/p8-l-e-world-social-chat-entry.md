# P8-L-E World social author profile and letter Chat entry

Status: **PR #221 FOLLOW-UP HOTFIX IMPLEMENTED IN WORKTREE · EXACT-HEAD LOCAL RECERTIFICATION IN PROGRESS · ISSUE #220 OPEN · BRANCH `feat/p8-l-e-world-social-author-profile-chat-entry` · DRAFT PR #221 · USER GATE/READY/MERGE PENDING**

P8-L-E closes the World social author-to-Chat entry path without pulling forward message send, response generation, streaming, retrieval, or Memory. A Feed/post/reply author is linked only when the backend supplies an exact same-World `world_character_id` and `author_profile_capability=available`. The post row remains the post-detail target; its avatar and name are separate semantic links to `/worlds/{worldId}/characters/{worldCharacterId}`.

The profile identity shell is owned by `features/characters`. Its current-World activity read model and presentation are owned by `domains/social` and `features/social`: four exact counts (`post_count`, `reply_count`, `liked_post_count`, `received_like_count`) and three cursor-paged tabs (`posts`, `replies`, `likes`). Received likes remain count-only. The repository resolves the exact active WorldCharacter, filters to the requested World, and excludes blocked, deleted, hidden, or otherwise non-visible sources. The public World profile reuses social rows without importing owner-only profile edit, autonomy, runtime, settings, or follow controls.

Phone scrolling is preserved while the `DeviceFrame` scroll owner hides the visible scrollbar and removes the stable gutter reservation. The Characters directory icon uses a dedicated metadata selector so the people glyph remains centered in its tile. Next, static frontend, and Tauri accept the same canonical profile route.

Tauri same-window history now carries a product-route index. On popstate, the browser URL is synchronized back into the desktop window route store before the static router snapshot is read. The profile back control therefore returns to the actual Feed or Characters origin; a direct profile entry with no prior product route falls back only to the current World's Characters directory.

The letter CTA is owned by `features/chat/public.ts`. It reads the typed chat-entry capability for the selected responding WorldCharacter and reuses P8-L-D's idempotent active thread create-or-get operation. Requester resolution is fail-closed:

```text
zero    → 조종 Character 연결 안내, thread 생성 금지
one     → 정확한 requester/responding WorldCharacter tuple로 create-or-get
anomaly → identity 정리 안내, thread 생성 금지
self    → 금지
blocked → 금지
inactive/cross-World target → profile/chat-entry 404
```

The browser boundary uses an immediate in-flight guard as well as a disabled loading state, while the backend unique active role tuple remains the authoritative replay/concurrency defense. The clicked post or reply is navigation origin only; no social source is injected into Chat evidence by this stage.

## Verification

The focused local Gate covers:

- backend profile, exact social author capability, chat-entry 0/1/N, self, blocked, inactive, cross-World, create-then-reuse, and duplicate-row count;
- Next Feed author avatar/name → profile → letter → canonical World Chat, double-click request count, and back-stack restoration;
- exact current-World four-count/three-tab activity, pagination, blocked/hidden/cross-World exclusion, and no owner controls or Chat composer;
- Phone hidden-scrollbar/no-gutter computed contract with real wheel scrolling, centered Characters icon geometry, and the visible profile back button;
- zero/anomalous requester guidance without a create request;
- static/Tauri route parity, profile → back → origin route-store synchronization, and the same profile → letter → Chat path;
- frontend typecheck/lint, Next/static build, Rust product-window route tests, inventory drift checks, and broader regressions.

The pre-Hotfix exact-head closeout remains append-only historical evidence: backend full `1,551 passed / 22 skipped`, focused contract and inventory `57 passed`, Next browser `20/20`, static/Tauri browser `63/63`, frontend lint·typecheck·Next build·static export PASS, Rust `product_windows` `7/7` plus `cargo fmt --check`, and current ER0·L4·backend architecture·frontend architecture/design·route-security·P8-L-D/E inventories. It is not reused as proof for the correction tree. The new exact-head full local and Hosted recertification will replace this paragraph's current-tree status after the correction commit exists.

The machine-readable successor inventory is `p8-l-e-world-social-chat-entry-inventory.json`. It chains the frozen P8-L-D inventory and records the stage's route, feature ownership, capability, fail-closed, and non-scope contracts.

PostgreSQL-specific concurrent create-or-get remains separately **NOT VERIFIED**; P8-L-D's SQLite/file-backed and backend uniqueness evidence is reused, not relabeled as PostgreSQL proof.
