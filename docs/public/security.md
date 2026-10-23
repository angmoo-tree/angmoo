# Local security model

Angmoo stores application state on the installation. Enabled provider features
send the necessary request content to the chosen provider. Local deployment does
not imply offline AI execution or immunity to other software on the device.

## Credentials and access

Keys are write-only inputs in supported management APIs. Read responses return
status and fingerprints; storage uses protected credential envelopes or token
hashes. Keep the root secret and encrypted data together in protected backups.
Do not print raw credentials, cookies, authorization headers or private request
content in logs, URLs, DOM previews or public artifacts.

Preserve local owner, World membership, source-version and deletion checks on
every supported path. Client state and disabled buttons are not authorization.
Use documented loopback bindings and Origin/Host/session protections; exposing a
local port remotely requires a separate security design.

## Untrusted inputs

Character cards, World Packages, model output and imported images are input data,
not instructions to bypass validation. Check paths, bounds, content types,
declared capabilities and current ownership before applying them. A checksum
proves file consistency, not the author's trustworthiness.

## Contributors and reporting

Public tests use synthetic data and fake providers. They do not receive personal
databases, hosted credentials, private runbooks or live provider keys. Security,
provider, trace, worker and migration changes need their applicable negative
cases and [CI validation](../operations/ci-validation.md).

Report vulnerabilities through [SECURITY](../../SECURITY.md). Keep personal
backups, real packages and raw logs out of public Issues.
