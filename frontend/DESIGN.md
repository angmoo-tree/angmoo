# Angmoo Frontend Design

Angmoo uses a responsive UI that makes posts and conversations easy to read and explains local runtime
state and user choices clearly. Next and static/Tauri share screens, states, and interactions. This document
defines current visual and interaction rules. Follow [ARCHITECTURE](ARCHITECTURE.md) for code placement and import direction.

## Principles and order of application

First check product authorization, data, execution contracts, supported paths, native security, and accessibility.
Then apply this design, semantic tokens, and shared components. An old screen's appearance does not authorize new functionality or permissions.

- Keep posts, conversations, and characters central; avoid overwhelming the default UI with internal execution details.
- Distinguish saved settings from runtime state, and activity results from the next scheduled time.
- Show only actions, counts, and states supported by actual capabilities and responses.
- Do not present read failure as empty, an in-progress query as success, or an unaccepted action as running.
- Maintain English/Korean guidance and accessible names together. Do not silently translate user-authored content.

## Screens and windows

`ProductViewport` owns the `100dvh` height and supplies the body space below the native toolbar.
Regular content fills the available width up to 960 CSS px; wide workspaces use up to 1440 CSS px.
Do not reintroduce a fixed imitation phone outline, black frame, device shadow, or fixed aspect ratio.

| Screen | Presentation and navigation |
| --- | --- |
| Device Home | Actual World, Settings, and Studio entry points; no global 4-item bottom menu or empty reserved space |
| World | 5 tabs: World, Feed, Chat, Characters, Relationships; preserve the current World |
| World relationships | Relationship graph inside the World's header, tabs, and single content body |
| Creator Studio | Wide editing workspace and existing return navigation |
| Memory | Wide browsing, detail, and settings workspace with explicit scope |
| Settings/character creation | Only the navigation needed by that screen; no unnecessary global footer |

World Home owns the introduction and return to Device Home; non-home screens own content-specific headers.
Do not duplicate titles or generic shell headers. A retained `relationship-graph` window enum does not imply
that every relationship URL requires a separate window.

Native screens use ordinary opaque OS windows with resizing, maximize, and Snap support. The main window's
initial content size is 480×850 logical pixels, with a default minimum of 480×480 logical pixels. Adjust for
monitor work area, DPI, and actual window borders. CSS content-width limits are not native maximum-window
sizes or fixed aspect ratios. The native toolbar provides Back, Forward, document reload, Home, and internal
paths, using actual navigation history.

Give the main body one scroll owner. Dialogs, long JSON, and explicitly bounded lists may scroll internally,
but must not duplicate ownership of page height and the main scroll.

## Color and typography

[`src/styles/semantic-tokens.css`](src/styles/semantic-tokens.css)
is the color source of truth. Use the roles below instead of repeating the same values in individual screens.

| Role | Use |
| --- | --- |
| surface, text, border | Neutral hierarchy for content, metadata, inputs, and separators |
| brand-accent `#ff6b6b` | Approved social inline actions and brand emphasis |
| action-primary / on-action-primary | Positive actions such as create, enable, post, and save |
| action-dark / on-action-dark | Stop, disable, and strongly emphasized neutral actions |
| brand-soft | Background for selected navigation and filters |
| success, info, warning, degraded, danger | Semantically appropriate status, with cues beyond color |

Do not add raw colors unnecessarily. Move repeated values into semantic roles within the change's scope.
Do not widen allowlists or baselines to hide regressions. Exceptions for data colors or external assets need
an owner, reason, and review condition.

The current bright-coral palette has three bounded contrast exceptions:

| Exception | Allowed scope |
| --- | --- |
| `EXCEPTION-A` | Coral foreground for approved show-more controls, mentions, social inline actions, kickers, and positive aggregate hearts/counts |
| `EXCEPTION-B` | Coral background with white labels/icons on positive primary CTAs |
| `EXCEPTION-C` | Soft background with coral foreground for selected navigation, filters, indicators, and approved keyword chips |

White against `#ff6b6b` has a contrast ratio of approximately 2.78:1. This is an existing limited exception,
**not a WCAG AA contrast pass**. Do not extend it to general body text, metadata, avatar initials, graph
labels, status, danger, or focus-visible. Other accessibility requirements remain in force.
The exceptions also exclude scores, warning/error, disabled states and generic links.
The supporting `#ffb5b5` border or halo must not be the only focus-visible cue.

General UI uses a system font stack supporting English and Korean. Only the Home wordmark uses bundled
Quicksand Bold 700, with its original OFL notice preserved. Remote-font downloads must not be required for build or execution.

| Text role | Size/line height |
| --- | --- |
| Large hero | 36/44px |
| Page title | 28/36px |
| Section title | 24/32px |
| Card title | 20/28px |
| Feed author | 18/24px |
| Feed body | 18/28px |
| General body | 16/24px |
| Metadata | 14/20px |

Use a 4px base grid with spacing centered on 8px increments. Regular screen gutters are 16px; stream-row
padding preserves full-bleed separators. Reuse existing Card/Dialog radius and shadow primitives instead
of repeating large floating cards for every post.

Allow appropriate Korean line wrapping rather than forcing `keep-all` everywhere. Use dedicated wrapping
for long IDs, URLs, and time strings. Motion is brief and secondary, and removed under reduced-motion preferences.

## Shared controls and states

- Button/IconButton supports hover, pressed, focus-visible, disabled, and loading states.
- Targets are at least 44×44px; primary composer actions retain the existing 48px standard.
- Icon-only actions require accessible names; decorative icons use `aria-hidden`.
- Placeholders do not replace labels. Explicit sr-only labels must still connect to the actual input.
- Dialogs support focus trapping, Escape, and focus restoration. Deletion confirmation initially focuses Cancel.
- Toasts provide supplementary guidance; they are not the only error channel.
- Distinguish loading, empty, forbidden, not found, offline, degraded, error, and retry.
- Display confirmed server counts. Do not substitute 0 for failed, unmeasured, or unavailable values.

## World introduction and characters

World introduction follows this order: banner → name → genre/mood → one-line introduction → expandable
introduction → character photos/names → access to my profile. Missing or failed banners use the existing
default. The introduction initially shows 4 lines and expands without a separate vertical scroller.

Character lists distinguish the actual user from autonomous characters. Reuse existing profile, status,
and settings layouts and explain World-specific persistence scope. A name containing a particular word
does not grant official-account colors or permissions.

Character registration finishes with autonomy OFF. Optional activity settings, API keys, and image settings
are saved explicitly and separately. Finish/Skip does not save unentered values or enable activity. Partial
save failure preserves successful results and inputs; auth/runtime changes clear sensitive input.

Distinguish current state, emotion, source description, observation time, and recent/next activity. Preserve
the saved order and original text of routines and interests. Expansion controls provide `aria-expanded`
and keyboard focus. Activity ON, waiting for active hours, provider readiness, and scheduler failure are different states.

Distinguish stored instants from display time zones. Format times under the user's current environment
contract; do not show raw UTC strings as local time. Do not use raw result JSON or internal IDs as recent-activity titles, help text, or link targets.

## Feed and posts

The World Feed header shows the Feed title, existing Angmoo logo, and actual World user profile. Do not add
duplicate World descriptions, a separate header refresh, or unsupported Follow/repost filters.

Each row follows avatar → author/time → body/title → photos → supported actions → separator. Reading,
text selection, and internal buttons must not conflict with whole-row navigation. A single photo preserves
its original ratio and complete content; multiple photos follow supported grid rules.

The World composer directly posts as an owner-controlled character. It may share presentation with Global
Feed Cue, but its payload, API, and meaning differ. Show the actual author, required title/body, photo actions,
and Send. Do not add automatic focus or extra AI execution. The UI does not change server contracts such
as the World's 160-character title and 4000-character body limits.

World likes use actual server capabilities, counts, and viewer selection. Do not invent equivalent controls
on screens that expose only display aggregates. Replies connect to actual detail routes; unsupported
repost/follow/share actions must not appear as fake functionality.

Initial and additional loads use pages of 30 root posts. Separate additional loading, refresh, and single-root
summary lifetimes. Failed loading/refresh preserves the list and composer input. A failed query after a
successful post must not suggest reposting. Image completion and reaction updates preserve the item and reading position.

Post/reply details show the selected item and its public descendant replies. A user's reply stores that
selected item as its direct parent. Make hierarchy, time, and author identifiable without excessive indentation on narrow screens.

## Chat

Chat uses a counterpart header, right-aligned dark user bubbles, left-aligned light character bubbles, one
message scroller, and a rounded composer. Model selection uses a compact footer; memory and diagnostics use supplementary dialogs.

- Load the latest 50 messages initially and older history in pages of 50 by default.
- After prepending, preserve the message and screen position being read when the response arrives.
- New replies do not force a jump down while the user reads history.
- New-message guidance, return-to-latest, history loading, and retry use existing primitives and English/Korean copy.
- Preserve the draft and conversation after history-query failure. Do not resend an accepted message.
- Merge only committed messages and evidence after response storage; do not reread the entire history each time.
- Preserve intent to follow the latest conversation or read history through image loading, IME changes, and resizing.

Normal recognition/response waiting shows one Typing state after approximately 300ms. Acceptance alone
does not clear it; actual delta, terminal state, or scope termination does. Preserve explicit retry/photo removal
and draft retention on recognition failure.

## Memory and relationships

Show separate settings/readiness for memory storage, embedding keys, retrieval-data preparation, and
relationship review. An unsaved key or an ON indicator does not prove retrieval completed.

Memory details distinguish content, sources, thoughts, and retention state, as well as event time, source
scope, memory-creation time, and unknown values. Evidence delivery and actual model use are not the same success condition.

Inspect failed memory experiences within the current character/World scope. Explain recheck/discard
alongside preservation of the original activity. Distinguish stored, rejected, skipped, and unresolved results.
Internal IDs, manifests, and raw errors are not default user guidance.

Show relationship direction, reference character, and evidence with arrows and text. Distinguish ready,
empty, degraded, rebuilding, and unavailable. Do not disguise canonical fallback as a healthy graph.

## Images and advanced settings

Authenticated images start fetching near the actual Chat/Feed viewport, with layout space reserved first.
Provide explicit retry after failure and cancel/release blob URLs on scope changes. Stopping offscreen
image-status queries is different from cancelling server generation.

Distinguish local photo preparation, attachment, recognition, generation, and result delivery. Preserve
preview, photo removal, and body text. Photo handling alone does not post, send Chat, or call AI. Detailed
codec and size boundaries follow the [photo-processing contract](../docs/operations/local-photo-codec.md).

ComfyUI separates server connectivity from Partner authentication. Use a labeled editor for API JSON and
preserve invalid input. A connection check is not successful image generation. Downloading, applying,
saving, and executing examples are separate actions; do not automatically install required external nodes.

## Deletion, recovery, and user guidance

World-deletion confirmation shows the saved name, deletion/preservation scope, name confirmation, and an
independent confirmation checkbox. Scroll only the long body so Cancel/Delete remain accessible. Explain
that accepted deletion has no cancellation or restore. Optional package export is neither a full-history backup nor a required step.

Retry guidance describes the actual failed operation. Do not repeat writes after query failures or assert an
unverified provider/OS cause. Provide expandable diagnostic detail as ordinary text when useful, without
exposing keys, prompts, Base64, or SQL arguments.

## Accessibility and validation

Check minimum 44px targets, independent focus-visible, keyboard/IME behavior, modal focus restoration,
non-color status cues, 200% zoom, reduced motion, and English/Korean wrapping. Apply accessibility contrast
requirements outside the bounded coral exceptions; those exceptions are not a whole-screen AA pass.

Exercise the changed screen's normal, loading, empty, error, forbidden, degraded, and retry states. Narrow
widths of 360, 390, and 436px and a wide width of 1440px are browser-validation baselines, not fixed device
frames. Native changes also require resize, DPI, OS-caption, keyboard, and shutdown-semantics checks.

Use existing Playwright fixtures, fixed clocks, locales, time zones, and remote-request blocking. Distinguish
canonical pixel validation from OS-specific functional checks. Screenshot counts and earlier passes do
not establish current quality. Review intended visual differences before updating baselines.

See the [design reference](../docs/architecture/frontend-design-reference.md) for actual paths, asset attribution,
and reuse, and the [frontend change guide](../docs/public/changing-frontend.md) for the implementation workflow.

The local `scripts/ci/check_frontend_design_contract.py --check` command verifies
the design policy, source inventories and existing baseline. Run it for relevant
design changes; an old closeout status or document version is not current proof.
