# Frontend guide

The frontend is a Next.js application. New backend calls belong behind the
owning feature's `api` boundary or a canonical shared API adapter; legacy
`src/lib` facades are compatibility surfaces, not the target architecture. UI
components should not duplicate REST contracts.

[`frontend/DESIGN.md`](../../frontend/DESIGN.md) is the canonical visual and
interaction contract for user-visible work. The portable reference,
provenance, route/surface debt, raw-color baseline, and existing Playwright
harness are recorded in
[`docs/architecture/frontend-design-reference.md`](../architecture/frontend-design-reference.md).
The contract applies to future L5 and later frontend work as well as L4.5.

Keep the feature-first direction: route wrappers consume migrated features
through `features/<feature>/public`, while `shared/ui` stays product-neutral.
Next and the static/Tauri router must render the same feature component. A
hosted visual reference must be classified as `DIRECT`, `ADAPTED`, `LOCAL`, or
`REJECTED`; the label does not authorize an unreviewed source or asset copy.

For ordinary Local user routes, keep the UI-C shell boundary intact:
`shared/ui/DeviceFrame` is a neutral frame primitive,
`features/device-shell/DeviceShell` owns Phone chrome and the reviewed Local
route matrix, and the legacy `components/AppShell` only adapts existing route
wrappers to that feature. Do not add a second Browser/Tauri shell, reintroduce
desktop rails, or put Next-only destinations into Phone navigation. Creator
Studio and Relationship Graph remain dedicated wide surfaces.

Phone pages keep ownership of their own meaningful header; the compatibility
shell must not inject a duplicate generic title. Use `LocalProductLink` where
a hosted Next destination may be unsupported in static/Tauri, and bind
pagination or pull-to-refresh to the single Device scroll owner rather than
assuming document/window scrolling.

`ANGMOO_API_BASE_URL` points server-side proxy routes at the local FastAPI
process. `NEXT_PUBLIC_EXPERIMENTAL_IMAGE_ENABLED` is `false` by default.
Turning it on exposes the experimental image controls but does not enable the
backend worker or supply provider credentials.

The public build uses the system font stack and must succeed without a remote
font download. New default assets must be tracked, rights-cleared, and added to
the exporter and asset manifest.

Check the design and ownership contracts with:

```bash
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```
