Pull requests may be written in English or Korean.
Pull Request는 한국어와 영어 모두 사용할 수 있습니다.

## What changed

Describe the smallest user-visible or contract-visible change.

## Validation

- [ ] Focused backend tests
- [ ] Public backend suite when applicable
- [ ] Frontend lint/build when applicable
- [ ] No production credential or user data used
- [ ] Public exporter/security checks when the candidate tree changes
- [ ] Every commit includes a DCO 1.1 `Signed-off-by` trailer (`git commit -s`)
- [ ] I understand that accepted contributions are provided under
      `GPL-3.0-only` unless explicitly stated otherwise

## Hosted validation

- Hosted impact classification: `public-only` / `hosted-fast` / `hosted-full`
- [ ] This change does not require hosted validation
- [ ] `requires-hosted-validation` applies because this changes a provider,
      resident/prompt/trace, scheduler/worker/media, migration, credential,
      authentication, authorization, ownership, or privacy boundary

Private integration is started only by a maintainer after reviewing an exact
commit SHA. Public pull requests never receive private source or credentials.

Staging success is not production approval.
