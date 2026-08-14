# Contributing to Angmoo

Thank you for helping improve the Angmoo public experiment.

Issues and pull requests may be written in English or Korean. A Korean guide is
available in `CONTRIBUTING.ko.md`. The English documents are canonical when a
translation differs.

## Before opening a change

1. Read `docs/public/architecture.md` and `docs/public/contribution-map.md`.
2. Keep the change inside the public boundary.
3. Use synthetic data and fake providers.
4. Add or update the smallest relevant test.
5. Run the frozen-install, backend, frontend, and export checks that apply.

Do not submit production credentials, private user data, OpenClaw runtime
material, admin or maintenance controls, backups, logs, traces, uploads, or
hosted-infrastructure configuration.

## Pull requests

Explain the behavior being changed, tests run, and any remaining gap. Check
`requires-hosted-validation` when the change affects provider requests,
resident orchestration, prompts/traces, scheduler/worker/media behavior,
migrations, credentials, authentication, authorization, ownership, or
privacy.

Hosted validation is performed by a maintainer with synthetic data and limited
test credentials. Contributors are never given production DB, KMS, Oracle,
SSH, or hosted-service credentials. Staging success is not production
approval.

The public workflow classifies each pull request as `public-only`,
`hosted-fast`, or `hosted-full`. This classification does not start a private
workflow. When hosted validation is needed, a maintainer reviews and dispatches
an exact commit SHA from a maintainer-owned branch. Fork code never receives
private source, repository secrets, or production credentials.

The public repository is the canonical source for these contributions. A pull
request must pass all six required Public Actions jobs before merge:

- `hosted-impact`
- `backend-contract`
- `frontend`
- `quickstart`
- `security-export`
- `dependency-audit`

The `hosted-impact` result tells maintainers whether a separate private
integration run is needed. It does not expose or execute private source in the
public workflow.

## Contract changes

The REST API, Alembic chain, LangGraph state/result, community behavior,
credential security, and lease/retry behavior are preserved contracts.
Intentional breaking changes require prior maintainer approval, an explicit
migration when applicable, and release notes.

By intentionally submitting a contribution for inclusion, you agree that it
is provided under GPL-3.0-only unless you explicitly state otherwise.

Every contribution must certify the Developer Certificate of Origin 1.1 with
a `Signed-off-by` trailer. The usual command is `git commit -s`. The DCO
confirms that you have the right to submit the contribution; it does not
replace the project license.
