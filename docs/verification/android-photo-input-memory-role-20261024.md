# Android photo input, Memory subjects and default roles — local verification

Date: 2026-10-24. Branch: `fix/android-photo-picker-input`.

This record covers the workspace plan's P000–P079, M000–M011 and R000–R019.
The baseline is `da6d42f9417b060ff07c049981417600af620da6`; the verified product
source is `f9e7c507d37f2da595254c6406c0a4581b4dfe31`.
Local implementation, scoped automated checks, physical-device samples and
diagnostic cleanup are complete. Physical sample limits and one incomplete
counter capture are recorded below rather than treated as universal certification.

## Commits and boundaries

| Local signed commit | Change |
| --- | --- |
| `1f329aea087fd1e9c28c2d6d28eb5a23dafceb3c` | Memory subject selection by control mode |
| `76e83f3db8d3dcf0e779616134529fe7aed2ebb4` | English defaults, legacy role compatibility and original-text display |
| `f9e7c507d37f2da595254c6406c0a4581b4dfe31` | Bounded image input and saved profile previews |

The applicable workspace instructions, frontend `AGENTS.md`, `ARCHITECTURE.md`,
`DESIGN.md`, design reference/product-shell/preservation documents and backend
`ARCHITECTURE.md` were followed. Existing UI components are **ADAPTED**; new bounded
input controllers and diagnostics are **LOCAL**. Next and static/Tauri share the
same feature implementations. No separate mobile product implementation was added.

No branch publication, PR, remote CI, main merge, tag, release, registry upload,
Windows installation or phone image replacement is part of this result. The
phone's current Angmoo data, services, keys and autonomous-activity settings are
outside the fixture's API routes. The user accepted temporary CPU/RAM and USB
charging effects of the separate phone check; it is not a power-management trial.

## Implemented contracts

The selected provider-backed File is consumed once through a bounded stream,
before size/last-modified queries or Worker transfer. Feature controllers own the
policy; the shared reader does not decide World scope, authorization or codec rules.

| Input | Original byte cap | Preparation boundary |
| --- | --- | --- |
| Feed / Chat photo | 20 MiB | One 30-second deadline through the real Worker result |
| Character/profile avatar or banner; World icon or banner | 5 MiB | One 30-second read/decode deadline, existing crop sizes |
| Generation reference | 10 MiB | One 30-second input preparation deadline |
| Conditional user seed | 6,000,000 bytes | Existing 8,000,000-character Base64 transport cap; server-configured cap remains separate |
| Character-card PNG / JSON | 20 MiB | One 30-second read; original bytes and PNG metadata retained |

The reader retains at most `ceil(limit / 256 KiB)` owned blocks plus the exact final
buffer. That is not a bound on all browser/codec memory or a provider's native chunk.
Abort, timeout, late bitmap disposal, reader cancellation and Worker termination
preserve the primary result. No arbitrary two-second delay, repeated provider-file
read, forced Files-picker route, page reload or cache-busting query was added.
Owned-memory encoding and crop-output verification remain distinct from first
reading a provider-backed file. Non-image ZIP, lore and workflow inputs retain
their separate policies.

Read failure, size/format rejection, decode failure and preparation deadline have
appropriate English/Korean messages. Image preparation failure is not represented
as a missing AI recognition key. Existing text, attachment, auth/scope and late-result
guards remain in place.

Successful profile saves invalidate only the affected avatar/banner resource.
An authenticated GET refreshes a stable URL; the previous good image stays visible
during refresh or GET failure. Retry after a successful save retries the GET only.
Save conflicts do not resubmit or invalidate the preview. Scope changes, stale GETs,
old Blob URLs and unmount cleanup are handled explicitly.

Memory excludes `owner_controlled` subjects and includes `autonomous` subjects,
including an AI named `User` or one with autonomous activity OFF. Owner URLs,
owner-only Worlds and invalid scope do not issue owner Memory/settings/embedding
requests. User speech inside an AI character's evidence remains visible. No common
character-list API, memory storage or DB policy was changed.

New `no_specific_role` rows store `No role` and
`A character with no specific World role.`. The exact legacy Korean name/description
pair remains supported; mixed or arbitrary pairs remain invalid. Existing IDs,
links, text, hashes and policy flags are preserved. The historical v2→v3 migration
keeps its Korean behavior through version-local definitions. No new migration,
data-version bump or backfill was added. Package validation/import/export supports
both exact pairs without rewriting the archive. An older 0.1.1 reader can reject
a new English-default package; backward reading by the new code does not imply
forward compatibility of the old code.

Role display uses stored original text in either UI language. Missing role data is
not disguised as `No role`. Studio uses the actual reserved row once, with an English
fallback only when absent. Automatic SNS introductions/day-life text, user-authored
content, timezone and AI generation-language policies were not changed.

## Scoped local verification

Private evidence directory:
`D:/project_code/angmoo-workspace/.task-output/photo-input-implementation-20261024/run-01`.
`local-verification.json` records the latest result for each case;
`source-artifact-manifest.json` binds the product source, changed-file hashes,
Next/static build artifacts and 14 prepared-photo outputs.

| Check | Result and evidence |
| --- | --- |
| Bounded reader and deadline/cleanup | 29 passed; `reader-final.log` |
| Exact old hook versus new hook, real rendered pixels | Old stale preview reproduced; new refresh/retry/scope/URL cleanup passed; `private-resource-final/result.json` |
| Relevant browser cases, Next + static | 120 passed, 0 skipped in latest combined scope: 64 existing creator-copy cases + 28 photo/input cases + 28 Memory/role cases |
| Default-role backend contracts | 40 distinct cases passed, 0 skipped; `backend-role-final.xml` plus corrected affected rerun |
| Actual browser-prepared photos through Post/Chat ASGI upload | 28 passed, 0 skipped; `backend-photo-roundtrip.xml` |
| Selected card/conditional-seed HTTP contracts | 4 passed, 0 skipped; `backend-input-final.xml` |
| Changed-file ESLint, project TypeScript, bilingual catalogs | Passed; closeout logs. Catalogs: 16 namespaces / 2,736 keys |
| Frontend architecture, backend dependency boundaries | Passed; 14 frontend features / 0 legacy violations; 1,604 backend modules / 6,953 edges / 0 legacy violations |
| Frontend design contract | Passed. Existing 11 canonical screenshot references and diff limits unchanged; two diagnostic screenshot calls added to inventory |
| Next production + static export builds | Passed; `NEXT_PUBLIC_EXPERIMENTAL_IMAGE_ENABLED=true` only in the isolated verification builds to expose conditional inputs |

The first broader card/seed run had 34 passes and 3 optional private-original
fixture skips. Those skips were not relabeled as passes; the final mandatory
synthetic HTTP selection is the separate 4/4 run above. Initial failed assertions
and their logs are preserved. A lossy WebP pixel assertion was corrected to codec
rounding tolerance; legacy migration expectations were pinned to Korean literals;
seed error text and an asynchronous intro-readiness assertion were corrected.
The Studio role row was also found to be stripped before its consumer and was
fixed in product code, then built and tested again. A failed attempt is superseded
only by the matching successful rerun, not by a broad success claim.

No full backend suite, full frontend suite, installer build, ARM64 image build,
remote CI or real AI generation was run. Backend checks used isolated test data
with external network denied. The browser fixtures deny unmatched requests and
never call the running phone backend or a provider.

## Physical phone verification

Device: Samsung SM-A528N, Android 14, Chrome 155.0.8059.87. The tested page uses
`http://localhost:13404`, reverse-forwarded to the PC's new frontend on port 3404;
the real installed application on `127.0.0.1:3000` is separate and retained.
Selection/read/Worker observations are passive: no forced read failure, metadata
override, delay or `setInputFiles` supplies the phone's photo choices.

| Physical check | Observed result and limit |
| --- | --- |
| Feed initial selection/repetition | 6 selected-file streams, 6 real Worker results and 6 fixture uploads. Five outputs share the same JPEG hash and one is a different PNG. User confirmed previews. Selection count is not a count of distinct photos. |
| Feed later cancellation/reselection | 6 streams, 4 completed Worker results and 4 fixture uploads. The actual preparation-cancel button was clicked after the first stream began and before any Worker transfer; the next selection completed. Three completed JPEGs match the earlier hash; the fourth is different. Final attachment preview measured 3072×4096. The remaining unmatched selection is not counted as a completed upload. |
| Chat | 5 selected-file streams, 5 Worker results and 5 local uploads/GETs. The user confirmed previews and picker-cancel/reselection. This is attachment preparation, not message transmission. |
| Creation Profile | User confirmed immediate avatar changes, banner display, crop cancellation preserving the old image, and reselection/Save. A later sample has 15 reads but only 3 independently captured saves across the two transports; they are not 15 completed saves. The strict same-mounted-component/stable-URL pixel assertion is the separate automated regression. |
| World icon and banner | Two icon uploads and two banner uploads recorded through the actual World controls; user confirmed both previews. My Profile buttons above these controls were distinguished from World media. |
| My Profile repeat replacement | After correcting the immutable-URL fixture, 4 saves and 4 distinct-image GETs: 2 avatars and 2 banners. User confirmed both repeated replacements without reload. |
| Generation reference and conditional seed | **USER_CONFIRMED** for both previews; the reference preview is also captured in `device-native-reference.png`. The test tab closed before final counters were retrieved, so exact read/upload counts and a seed screenshot are **NOT_OBSERVED**, not inferred from the user confirmation. |
| Character-card PNG | Android Files picker verified by screen capture. Three cards were selected; all three retained `chara` metadata in the isolated import. The final synthetic card is exactly 669 bytes and SHA-256 `6f644b21752ad3f29aeeb6290eb619b93581f2742fc223d1884ba82a33ea2539`, matching the file copied to the phone. User confirmed the imported name. This is not a photo-list-picker claim or a real character registration. |
| Memory / role display | **14/14 passed on physical Chrome**, with 0 unmatched requests. Four Memory cases cover both languages, type-based subjects, owner URLs, empty Worlds, user speech and late World responses. Ten role cases cover stored English/Korean names, descriptions, ordinary same-name roles, missing-role feedback, Studio fallback and language changes without World writes. |

`phone-verification.json`, `device-user-checks.jsonl`,
`device-feed-cancel-reselect-proof.json`, `device-feed-final-preview.json`,
`device-card-completed.json` and `phone-memory-role-result.json` retain the bounded
observations. The later Feed phase began about 33 minutes after the initial Feed
phase's final selection; other photo checks occurred between them. This does not
establish a cold provider cache. A newly captured/never-selected photo is
**NOT_OBSERVED**. Real read/decode errors did not recur in the captured successful
new-input samples; bilingual failure states were tested with controlled fixtures,
not manufactured on the phone. No page reload, forced Files route, sleep or changed
permission was used to make the photo-list sample pass. The Files path above is
the card input's own native picker.

Two fixture defects were investigated without changing product behavior to make
the check pass. A partial My Profile PATCH in the original World fixture replaced
omitted display-name/handle fields with `undefined`, producing a fallback-initial
render error. The real `OwnerControlledIdentityService.patch` uses `exclude_unset`
and merges only submitted fields; the isolated transport was corrected accordingly.
The My Profile fixture also reused one immutable asset URL for different uploads,
so repeat previews remained stale. The real `save_profile_media_bytes` creates a
new `uuid4` filename on every successful save. After matching that identity
contract, the phone recorded four uploads and four distinct-image GETs (two
avatars, two banners), and the user confirmed immediate replacement. Five picker
selections occurred; this is not described as five saved images. Stable **draft**
URLs remain stable in their fixture and are covered separately by the explicit
revision fix and rendered-pixel regression. No cache-busting or forced reload was
added to product code for either fixture incident.

Earlier controller-only problems are retained as well: a creation-form navigation
click met the mobile keyboard, and changing a draft transport halfway through a
sample left the PC fixture revision at 8 while the phone fixture had revision 9.
The latter caused the synthetic request failure; the fixture now keeps its own
revision consistently. The first Memory/role runner invocation used the workspace
working directory instead of `browser-tests`, so fixture loading failed before
any case ran. The correctly rooted run executed all 14 cases. These setup failures
are separate from image read failures, and were not addressed by product retries,
longer deadlines or skipped assertions.

Only diagnostic summaries and synthetic test assets belong in Git. User photos,
screenshots and raw local evidence are not committed. Initial Feed/Profile fixture
responses temporarily returned processed upload bytes through PC memory; they were
not written as source-photo files. Subsequent transport fixtures keep selected
image bytes in phone browser memory and return only result metadata to the PC.
This diagnostic change does not change product input/codec/crop code. Record this
distinction rather than claiming that the initial diagnostic used no PC image bytes.

## Closeout

`cleanup-receipt.json` records completion at 2026-10-24 13:29:12 UTC. Owned Next and
static processes (22288 / 9944) were checked against their command and creation time
before termination. Fixture controllers and the physical assertion runner exited.
The test tabs were closed; the original installed-app tab was retained. Only the
test's ADB forward 18294 and reverse 13404→3404 were removed. Both mapping lists
are empty and ports 3404, 3405, 18294 and 18295 have no listeners. The synthetic card
was hash-checked and removed; existing cards, SSH, Angmoo services/data and logs
were not removed or restarted.

P000–P079, M000–M011 and R000–R019 are closed within the approved local scope. The
workspace checklist links this record and explicitly carries the physical limits
above. Product SHA `f9e7c507…` remains the source bound to both builds and all listed
tests; the following documentation-only commit does not change those binaries.
The branch remains local. No push, PR, remote CI, main merge, deployment or device
image replacement was performed.

Passing these samples does not certify every Android provider/image, an unobserved
cold cache, a complete saved-photo transaction against the real phone backend, or
the unchanged installed 0.1.1 application. The new input behavior has been checked
in the new isolated frontend. Backend contracts are the separate synthetic ASGI/DB
checks above. This test added no real AI calls; pre-existing autonomous activity was
outside the fixtures and was not assessed or disabled.
