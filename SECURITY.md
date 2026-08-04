# Security policy

## Reporting a vulnerability

Use GitHub Private Vulnerability Reporting for security issues. Do not post a
credential, exploit, personal information, or an unredacted log in a public
issue, discussion, or pull request.

Include only the minimum reproduction information:

- affected revision and surface;
- impact and preconditions;
- synthetic reproduction steps;
- sanitized paths, status codes, and fingerprints.

Do not test against the hosted production service or other users' data without
explicit written authorization.

## Read-only principals

The public runtime does not expose a demo credential-exchange endpoint. It
does preserve the provider-neutral `auth_method="demo"` session contract and
locked-identity guards so a separately maintained hosted extension can issue
a time-bounded, read-only session. Authenticated `POST`, `PUT`, `PATCH`, and
`DELETE` requests are rejected for those principals, and locked identities
cannot use Local Bot tokens.

## Login and Local Bot abuse controls

Password signup is disabled by default. Password login uses database-backed,
keyed-HMAC throttle buckets so raw email and network addresses are not stored
in the throttle table. Set `LOGIN_THROTTLE_HMAC_SECRET` to a dedicated secret
for hosted use; when it is blank, `APP_SECRET` is used. Keep
`LOGIN_TRUSTED_PROXY_CIDRS` empty unless the exact reverse-proxy network ranges
are known and controlled by the maintainer.

Local Bot action and read quotas are also database-backed. Apply every Alembic
migration before running more than one backend process; process-local counters
are not a supported substitute.

## Response

The maintainer may pause publication, revoke or rotate affected keys, isolate
the vulnerable path, and investigate impact. User notification and production
response remain maintainer decisions. A public fix or advisory is published
after exposure risk is controlled.

The `v0.1.0` repository is an experimental release. Supported versions and
security-update windows will be stated in each GitHub Release.

## 한국어 신고 안내

보안 문제는 GitHub Private Vulnerability Reporting으로 비공개 신고해 주세요.
credential, exploit, 개인정보 또는 원문 log를 public Issue, Discussion, PR이나
커뮤니티 댓글에 올리지 마세요. 신고는 한국어나 영어로 작성할 수 있습니다.

영향받는 revision과 기능, 영향과 전제조건, synthetic 재현 절차, 민감정보가
제거된 path·status code·fingerprint만 포함해 주세요. 명시적인 서면 승인 없이
hosted production이나 다른 사용자의 데이터를 대상으로 테스트해서는 안 됩니다.

### 읽기 전용 principal

Public runtime은 demo credential 교환 endpoint를 제공하지 않습니다. 대신 별도로
관리되는 hosted extension이 유효기간이 있는 읽기 전용 session을 발급할 수 있도록
provider-neutral `auth_method="demo"` 계약과 locked identity guard를 유지합니다.
해당 principal의 인증된 `POST`, `PUT`, `PATCH`, `DELETE` 요청은 거부되며 locked
identity는 Local Bot token을 사용할 수 없습니다.

maintainer는 필요하면 공개 절차를 중단하고 관련 key를 폐기 또는 회전하며
영향 범위를 조사합니다. 사용자 통지와 production 대응은 maintainer가 최종
결정합니다. 영어 정책과 번역 내용이 다르면 영어 정책을 기준으로 합니다.
