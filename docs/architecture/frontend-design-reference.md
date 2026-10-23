# Frontend design reference and provenance

This document explains how to reuse a visual reference without importing its
product assumptions. The current rules live in
[DESIGN](../../frontend/DESIGN.md); implementation ownership lives in
[ARCHITECTURE](../../frontend/ARCHITECTURE.md). Older screenshots and migration
results explain decisions but do not override current routes or capabilities.

## Classify the reference

| Classification | Meaning | Example |
| --- | --- | --- |
| DIRECT | Reuse a reviewed visual anatomy with the same meaning | Author, time, body and divider hierarchy |
| ADAPTED | Reuse the anatomy while changing product semantics explicitly | A World-scoped profile or direct post composer |
| LOCAL | Design for an Angmoo Local capability | World import, local readiness, Memory controls |
| REJECTED | Do not adopt behavior unsupported by the local product | Hosted account quotas, fake actions, remote administration |

The label is not permission to copy unreviewed source, artwork or fonts.
Record the source, relevant license and the accepted part of the reference.
Do not depend on a sibling private checkout or a live hosted page at build time.

## Current product choices

- The common viewport is responsive; the retired decorative phone frame is not
  a target for new screens.
- Device Home uses World/tool entry points. World navigation owns five sections.
- World relationships render inside their World surface. Studio and Memory keep
  their wide workspace contracts.
- World direct posting and Global Feed Cue may share visual anatomy but have
  different APIs, ownership and effects.
- World likes use the actual capability and stored result. A read-only metric
  elsewhere is not permission to add a mutation control.
- Chat and Feed use bounded pages, preserve reader intent and defer downloading authenticated
  images until they are near the viewport.
- User-visible labels are English/Korean; content created by users or characters
  remains original text.

Use the actual source route and owner instead of a dated reference tree. Retired
`features/*/public`, `shared`, `ui` and `model` layouts are not templates for new
code. Composition joins features through explicit values and slots.

## Tokens, icons and fonts

The existing semantic token file is the authority for color roles. A new screen
does not create a separate palette. The three bounded bright-coral contrast
exceptions remain exceptions; do not describe them as WCAG AA compliance or
extend them to body text, state labels or focus indications.

Reuse bundled first-party Angmoo assets and existing icon primitives. Record new
file identity, source, rights and notices in the repository's asset inventory.
Remote build-time assets are not allowed. Runtime user media stays behind the
supported authenticated media path.

General UI uses the system font stack. The approved Home wordmark uses locally
bundled Quicksand Bold 700 with its original OFL notice. Do not make that font a
new global Korean text dependency.

README branding is documentation artwork, separate from a product UI redesign.
Use a first-party wordmark with its original proportions and accessible text.
An old app screenshot must not be presented as the current released interface
without checking its source, language and visible private content.

## Current inventories and data contracts

The [design policy](../../security/frontend_design_policy.json) owns adoption
classification, semantic primitives, route capabilities, color exceptions and
visual fixture identities. Its DIRECT / ADAPTED / LOCAL / REJECTED classifications
refer to specific reviewed reuse, not to an entire upstream product.

Use [`next-static-compatibility.json`](next-static-compatibility.json) together
with that policy to distinguish route existence from a supported runtime surface.
The semantic foundation lives in `frontend/src/styles/semantic-tokens.css`,
`frontend/src/components/ui/` and the deterministic
`frontend/src/features/ui-foundation/components/semantic-foundation-fixture.tsx`.
The existing `/ui-foundation` fixture remains excluded from search indexing.

The raw-color scan covers sorted `.css`, `.ts` and `.tsx` files under
`frontend/src`, using the expression below. Its final word boundary excludes SVG
fragment references such as `url(#beak)`. Keep additions at zero, review touched
consumers and lower the tracked baseline when an intentional migration removes debt.

```regex
#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{5}|[0-9A-Fa-f]{3}|[0-9A-Fa-f])?\b
```

`ManualSocialPostRead.reply_count` and `like_count` are server projections.
Display confirmed values and distinguish aggregate counts from a viewer's own
reaction. An aggregate-only surface does not gain a mutation just because a
different World surface supports likes. Preserve actual write capabilities.

Playwright dependencies belong to `browser-tests`. Its Next, static and visual
projects share reviewed fixtures while retaining runtime-specific assertions.
The three contrast exceptions in DESIGN are **not a WCAG AA contrast pass**;
neither a fixture image nor a historical successful check changes that boundary.

## Visual verification

Use the existing `browser-tests` fixture server, corpus and Playwright projects.
Keep the fixture clock, locale, timezone, reduced motion and network restrictions
deterministic. Only explicit synthetic operations needed by the fixture may be
mocked; a visual check must not call a live AI provider or use personal data.

The canonical pixel environment is the pinned environment recorded by the test
configuration. A Windows functional screenshot does not establish a passing result
against the Linux baseline. Next production and static export protect different consumers of the same
screen and both need coverage when the shared behavior changes.

Review intentional changes at the affected narrow and wide viewports. Verify
focus, 200% reflow, reduced motion, long Korean/English text, loading, empty,
forbidden, offline and degraded states as appropriate. Native DPI and actual
window behavior need separate checks when changed.

Do not broaden pixel tolerances, add fake counts or delete a supported route to
obtain a green result. Update only reviewed baselines for intentional visual
changes; keep the original proof in Git history rather than a growing dated
status ledger in this document.

## Contributor workflow

1. Identify the affected surface, feature owner and runtime consumers.
2. Record DIRECT/ADAPTED/LOCAL/REJECTED and the actual source being reused.
3. Reuse semantic tokens, existing primitives and shared feature components.
4. Preserve capability, scope, read/write and resource-lifetime contracts.
5. Update English/Korean labels and accessible names together.
6. Run the affected architecture/design, type, build and browser checks.
7. Describe intentional visual differences and any unmeasured native/user cases.

Historical implementation reports remain separate records. They are not a
requirement to keep old source text, old snapshot counts or completed work stages
inside the contributor contract.
