# Public security model

Contributor and fork CI use synthetic data, local credential encryption, and
fake providers. They receive no hosted credential, production database, KMS,
Oracle, SSH, or user-data access.

Raw keys are write-only inputs. Read responses expose fingerprints and
booleans, while persistence stores encrypted envelopes or token hashes.
Secrets must not appear in logs, traces, URLs, DOM state, browser storage, or
test artifacts.

The final exporter reads exact blobs from a selected Git commit, rejects
unclassified files in watched source areas, and creates a history-free tree.
The project scanner and Gitleaks must both report zero fatal findings for the
candidate and its fresh Git repository.

Changes to credentials, authorization, privacy, providers, workers, prompts,
traces, or migrations require maintainer hosted validation.
