# Security policy

## Supported delivery from 0.1.5

Docker on Linux amd64/ARM64 (including Windows Docker Desktop) and experimental
Termux ARM64 remain the supported delivery paths. New native Windows installers
and official native Windows support end with 0.1.5. Historical binaries, source
and manual checks are retained; their availability does not promise ongoing
security updates. Keep existing data and backups. No Windows-native-to-Docker
migration tool is provided; Docker starts with separate, empty data.

0.1.5부터 Docker와 실험 지원 Termux를 배포 경로로 유지합니다. Windows 네이티브
설치본의 신규 배포·공식 지원은 중단하며, 기존 파일·코드·수동 검사는 보존합니다.
기존 설치본을 계속 내려받을 수 있다는 사실이 향후 보안 업데이트를 보장하지는
않습니다. Windows 설치판에서 Docker로 옮기는 이전 도구는 제공하지 않으므로
Docker에서는 새 환경으로 시작하며, 기존 데이터와 백업은 따로 보존하세요.

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

Use the versioned three-service Compose configuration or Termux launcher. PostgreSQL
17, pgvector and protected DB credentials are part of the installation. The
runtime DB role has no superuser, role-creation or schema-creation privileges.
Docker DB ports are internal; Termux and historical native Windows DBs bind to loopback.
Preserve all DB, media, root-secret and credential volumes/files together.
Docker/Termux 0.1.4 → 0.1.5 preserves PostgreSQL data through the normal update path.
Official 0.1.3 SQLite input uses the historical 0.1.4 migration tool. Do not apply
historical hosted Alembic revisions or start competing backends on one root.

Before diagnosing an installed Windows payload or database, confirm the actual
installation and opened paths using the project's installed-app diagnostic
procedure. A redirected or stale path alone is not evidence of data corruption.
Use [migration](docs/public/postgresql-migration.md) and
[PostgreSQL backup/recovery](docs/public/postgresql-backup.md). The
[SQLite recovery guide](docs/operations/sqlite-recovery.md) applies only to
0.1.3 and preserved migration inputs. Diagnose termination before removing work,
locks or data. Never publish DSNs, passwords, journals or migration exports.

## Contributor security checks

Use synthetic data and fake providers for public tests. Secret scanning,
dependency and license checks, authorization tests, migration checks and build
provenance protect different boundaries. A passing check does not certify all
security properties. Fix the cause of a check failure rather than broadening an
allowlist or disabling verification.

Consult the release notes and repository security advisories for affected
versions and available fixes. This policy does not promise a response deadline
or indefinite support for every historical build.
