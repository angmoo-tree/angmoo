# Contributing to Angmoo

Thank you for helping improve Angmoo. The canonical repository is
`angmoo-tree/angmoo`. Issues and pull requests may be written in English or
Korean; the English guide is canonical if translations differ.

## Before opening a change

- Read `docs/public/architecture.md` and `docs/public/contribution-map.md`.
- Start from the latest `main` in a branch or fork.
- Use synthetic data and fake providers. Never submit credentials, personal
  data, raw logs, backups, or a local user's World Package.
- Add or update the smallest relevant deterministic test.
- Keep unrelated refactoring out of a behavior change.

An Issue before implementation is recommended for features, bugs, and
structural changes so scope can be agreed first. Small documentation and typo
fixes may open a pull request without an Issue. Issue linkage is not enforced
mechanically. When an Issue exists, use `Closes #number` or an explicit
reference in the pull request.

## Local setup and checks

Install only from the committed lockfiles:

```powershell
uv sync --frozen --directory backend
pnpm --dir frontend install --frozen-lockfile
```

Run the checks that cover your change. The complete Local OSS gate is:

```powershell
uv run --project backend python scripts/check_ci_policy.py
uv run --directory backend python -m pytest -q
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

PostgreSQL and Neo4j checks use disposable local services. Provider-dependent
tests use fake providers and must not make external model calls.

## Pull requests and merge ownership

Every change reaches `main` through a pull request. The ten required checks
are:

- `backend`
- `frontend`
- `migration-postgres`
- `local-core-smoke`
- `local-autonomy-smoke`
- `local-full-graph`
- `oss-boundary`
- `dependency-license`
- `dco`
- `architecture-boundary`

`windows-local-smoke` and `codeql` remain advisory checks. Advisory does not
mean ignored: failures and promotion conditions must be documented and
security findings must be resolved or explicitly triaged.

External contributors submit pull requests and cannot push to or merge
`main`. The repository owner performs the final review and merge after required
checks pass and conversations are resolved. During the single-maintainer
period, `required approvals: 0` avoids requiring an impossible self-approval;
it does not remove owner review or give contributors merge authority.

## License and DCO

Accepted contributions are provided under `GPL-3.0-only` unless explicitly
stated otherwise. Every human commit must certify the Developer Certificate of Origin 1.1 with a `Signed-off-by: Name <email>` trailer. Use:

```powershell
git commit -s
```

The DCO 1.1 confirms that you have the right to submit the contribution; it
does not replace the project license. Dependabot receives only the narrow bot
exception enforced by the repository checker.

## Contract and architecture changes

REST/OpenAPI, Alembic, routine/social/graph contracts, authorization,
credentials, lease/retry, and user-data boundaries are compatibility surfaces.
Intentional breaking changes require an Issue, migration or compatibility plan
when applicable, focused tests, and a clear rollback path.

T2.5 adds the incremental domain-first contract in
`docs/architecture/backend-domains.md`. Before adding backend behavior, choose
the owning domain or runtime area there. Cross-domain imports must use
`app.domains.<name>.public`; do not reach into another domain's internal module
or add a dependency on the horizontal `services`, `models`, `schemas`, or
`cruds` paths.

The import inventory records facts, while `security/architecture_import_policy.json`
records target rules and exact reviewed legacy exceptions. Existing exceptions
may shrink but must not grow merely to make CI pass. Run:

```powershell
uv run --project backend python scripts/ci/generate_architecture_inventory.py --write
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --directory backend python -m pytest -q tests/test_t2_5_architecture_boundaries.py
```

Keep structure-only PRs focused. Do not mix behavior changes, migrations,
provider configuration, dependency majors, transaction semantics, bulk
formatting, or Hosted/Private/Production settings into a package-move PR.

Report vulnerabilities through the private process in `SECURITY.md`, never a
public Issue.
