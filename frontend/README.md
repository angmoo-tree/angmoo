# Angmoo frontend

The frontend supports English and Korean in the Docker/Termux browser UI and
the Windows Tauri application. Next.js and the static application share feature
components; they do not have separate implementations of Chat, Feed or Memory.

## Start development

From the repository root:

```sh
docker compose -f compose.yml -f compose.dev.yml up --watch
```

Open http://127.0.0.1:3000. For host tooling or native window changes, follow
[development](../docs/public/development.md) and
[Windows Host Tauri dev](../docs/public/windows-host-tauri-dev.md).
Use the Node and pnpm versions pinned by the repository when running host tools.

## Before changing a screen

- [ARCHITECTURE](ARCHITECTURE.md): feature ownership, composition and resource lifetime.
- [DESIGN](DESIGN.md): current layout, semantic tokens, interactions and accessibility.
- [Product shell](../docs/architecture/frontend-product-shell.md): routes, viewport and native navigation.
- [Design reference](../docs/architecture/frontend-design-reference.md): adoption and asset provenance.
- [Changing the frontend](../docs/public/changing-frontend.md): a focused implementation workflow.

`src/app` owns Next entry points; `src/composition` joins features;
`src/features` owns product behavior. `components`, `hooks`, `lib`, `types` and
`utils` hold appropriate common code. Import concrete owner files, not retired
feature facades. UI strings and accessible names need English and Korean.

## Verification

Select lint/type checks, builds and browser cases according to the affected
feature and execution path. Common screens need Next and static coverage. The existing Playwright
project is `../browser-tests`; do not create a second unconnected test runner.
Documentation-only edits need command/link/contract review, not an automatic
full frontend run. Remote checks follow [CI validation](../docs/operations/ci-validation.md).
