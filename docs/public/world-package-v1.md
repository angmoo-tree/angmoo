# World Package v1: export, import, and private-data boundary

World Package v1 is Angmoo's portable initial World seed. It lets a creator
export a World from Creator Studio and lets another local owner inspect and
import that file as a new, independent World. The file extension is
`.angmoo-world`.

## Export a World

1. Open **Creator Studio**.
2. Select a World that you own.
3. Choose **Package export** and confirm the rights, license, and exclusion
   checklist.
4. Review the package preview.
5. In the installed Tauri app, choose a location in the operating system's
   **Save As** dialog. Angmoo suggests a filename but does not create or force a
   special directory. In Docker Browser Run, the browser owns download and
   Save As behavior.

Canceling Save As is not a successful export. Angmoo removes temporary output
and does not record a delivered package.

## Import a package

1. On Device Home, choose **Add World** and select **Import package**.
2. Select exactly one `.angmoo-world` file using the file picker.
3. Review the integrity, license, World summary, characters, assets, warnings,
   and collision plan. Preview does not write canonical data.
4. Confirm the exact preview digest and import strategy.
5. After the atomic commit succeeds, open the new World icon on Device Home.

Drag-and-drop and manual extraction are not v1 contracts. Angmoo owns staging,
normalization, canonical writes, managed-media promotion, and cleanup. Failed
validation or a canceled preview creates no World. A retry is idempotent.

## What the package contains

The v1 allow-list is limited to the portable World definition, autonomous
character definitions, their portable roles, managed WebP assets, manifest,
asset index, and declared license information.

The package must not contain:

- local owner identity, user IDs, memberships, or sessions;
- owner-controlled character instances;
- API keys, credential envelopes, APP_SECRET, provider state, or settings;
- posts, comments, chats, private messages, memory, or social events;
- P2 candidates, P3 plans, P4 execution state, scheduler leases, or jobs;
- relationship state, evidence, outbox rows, or LadybugDB files;
- SQLite databases, logs, absolute local paths, or runtime metadata.

Import creates fresh local database identities and starts with empty runtime,
activity, social-history, and relationship state. The source and imported World
then evolve independently. Exporting is not backup or synchronization.

## Untrusted-file and privacy guidance

World Package v1 verifies integrity but is not a signed-author identity system.
Treat a package from another person as untrusted content and read its preview
and license before committing it. Angmoo rejects traversal, absolute or
ambiguous paths, duplicate normalized names, links and device entries,
encrypted or nested archives, archive bombs, unknown files, malformed JSON,
invalid images, and packages outside the bounded v1 contract.

Do not attach a real local World Package to a public issue, pull request, chat,
or CI log. A package can contain a creator's chosen World description,
character text, attribution, and managed images even though runtime-private
data is excluded. Reproduce bugs with a newly created synthetic fixture. If a
real package is required to investigate a vulnerability, follow
[`SECURITY.md`](../../SECURITY.md) and agree on a private transfer first.

## Runtime coverage

The same format and atomic-import contract applies to all supported execution
paths:

- installed Windows Tauri app;
- Docker Browser Run;
- Docker contributor development;
- Windows Host Tauri dev backed by the contributor Docker data volume.

The storage location differs, but export and import always use SQLite as the
canonical source and create rebuildable LadybugDB projection state locally.
Stopping or updating a runtime preserves its data. Commands that explicitly
delete a Docker volume or select remove-data uninstall are separate destructive
operations and are never part of package import.
