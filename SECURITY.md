# Security policy

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/angmoo-tree/angmoo/security/advisories/new).
Reports may be written in English or Korean.
Do not disclose an exploit, credential or personal data in a public Issue.
If a private report cannot be submitted, request a private contact channel
without publishing sensitive details.

Include the release version or commit, operating system, installation method,
affected behavior, expected security boundary and a minimal synthetic
reproduction. Share safe error codes and redacted diagnostics. Do not attach
personal databases, API keys, session tokens, backups, real World Packages or
unredacted service logs.

## Local data and credentials

Angmoo stores application data on the device where it is installed. Configured AI requests send
the content needed by that request to the selected provider. Local storage does
not mean every enabled feature operates without a network.

Credential read responses expose status or fingerprints, not stored plaintext.
Keep the installation's secret material together with its protected backup;
encryption does not make a backup safe to publish. Keep services on their
documented loopback bindings. Remote access requires its own threat model and
must not be enabled by disabling Origin, Host, token or authorization checks.

World Packages transfer creator-selected initial content, not a complete
application backup. Review their content and license before sharing or importing.

## Updates and recovery

Use the official versioned installer or image pair and preserve the data root or
Docker named volume. Supported Local upgrades use the embedded SQLite migration
chain. Do not apply historical PostgreSQL Alembic migrations to a Local database
or start competing backends against the same data root.

Before diagnosing an installed Windows payload or database, confirm the actual
installation and opened paths using the project's installed-app diagnostic
procedure. A redirected or stale path alone is not evidence of data corruption.
Use [SQLite recovery](docs/operations/sqlite-recovery.md) for contention and
retained-result boundaries. Diagnose unexpected termination before manually
removing locks, pending work or data.

## Contributor security checks

Use synthetic data and fake providers for public tests. Secret scanning,
dependency and license checks, authorization tests, migration checks and build
provenance protect different boundaries. A passing check does not certify all
security properties. Fix the cause of a check failure rather than broadening an
allowlist or disabling verification.

Consult the release notes and repository security advisories for affected
versions and available fixes. This policy does not promise a response deadline
or indefinite support for every historical build.
