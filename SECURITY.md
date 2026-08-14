# Security policy

## Reporting a vulnerability

Use [GitHub Private Vulnerability Reporting](https://github.com/angmoo-tree/angmoo/security/advisories/new).
Do not put credentials, exploits, personal information, local database dumps,
World Packages, backups, or unredacted logs in a public Issue, Discussion, or
pull request.

Include only the minimum sanitized evidence:

- affected revision, operating system, and Local profile;
- impact and preconditions;
- synthetic reproduction steps;
- redacted paths, status codes, and fingerprints;
- whether local user data, BYOK credentials, or backups may be affected.

Do not test systems or data you do not own without explicit authorization.

## Local data and BYOK boundary

Angmoo is a local-first application. The operator is responsible for access to
the device, database services, backups, and imported World Packages. Provider
keys are user-supplied BYOK secrets and must remain outside source control,
Issues, PRs, logs, fixtures, and screenshots. Use synthetic fixed values only
where an exact path+rule+value exception is reviewed by the repository policy.

Backups can contain posts, comments, relationships, memories, routines,
credentials, and World data. Store and dispose of them as sensitive user data.
Deleting a UI record does not prove that an independent backup was erased.

## Supported security controls

The repository runs secret/history scans, dependency and license audits, DCO
verification, Local OSS boundary checks, and CodeQL triage. Local Bot and login
abuse controls remain database-backed. Apply every Alembic migration before
running multiple backend processes; process-local counters are not a supported
substitute.

## Response and supported versions

The maintainer may privately reproduce the issue with synthetic data, isolate
the affected path, revoke test credentials, prepare a forward-fix PR, and
publish an advisory after exposure risk is controlled. No hosted production
incident-response service is promised by this repository.

Supported versions and security-update windows are stated in GitHub Releases.

## 한국어 신고 안내

보안 문제는 [GitHub 비공개 취약점 신고](https://github.com/angmoo-tree/angmoo/security/advisories/new)를
사용해 주세요. credential, exploit, 개인정보, 로컬 DB dump, World Package,
backup, 원문 log를 public Issue·Discussion·PR에 올리지 마세요.

영향받는 revision과 OS, Local profile, 영향과 전제조건, synthetic 재현 절차,
민감정보를 제거한 path·status code·fingerprint만 전달해 주세요. BYOK key와
backup은 사용자의 민감한 로컬 데이터이며 source·Issue·PR·log에 복사하지
않습니다. 명시적 승인 없이 다른 사람의 시스템이나 데이터를 시험하지
마세요.
