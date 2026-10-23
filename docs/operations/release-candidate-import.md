# Release candidate import compatibility

The loader chooses the supported Docker image transport before loading.
Containerd stores consume the verified OCI archive directly. Classic stores use
the pinned Skopeo converter to create a temporary Docker archive, then load it
through the host Docker CLI. Conversion has no network or Docker socket access.
The original OCI archive, provenance and SBOM remain the promotion inputs.

## Identity and failure handling

1. Verify source, archive hash and OCI payload before importing.
2. After loading, verify architecture, config digest and every rootfs diff ID.
3. Use platform selectors only when both CLI and daemon support API 1.49;
   otherwise retain the same checks on architecture-specific tags.
4. Stop on conversion, load or storage failure. Do not switch transports after
   an arbitrary error or write a success receipt for a partial import.
5. Keep temporary transport space beside the candidate, convert one image at a
   time and clean up owned temporary files afterward.

A successful compatibility experiment with an older image does not validate a
new product candidate. Use the exact source and original bytes for release checks.

## Non-root feature-test staging

The host temporary parent remains private. Prepare a dedicated input subdirectory with traversal permission
(mode 0755) for `docker cp`; copying a root-owned 0700 directory would deny
the image's non-root test user access. Keep the image's original user and disabled
external networking. Do not solve staging failures by running the product as root.

Stage only synthetic test inputs and hash-verified, lock-pinned test tools.
Do not modify `/app`, production dependencies, personal data or the original
archive. Failed or skipped required tests do not produce a success receipt.

## Validation and publication

Follow the [CI guide](ci-validation.md) and [publishing procedure](release-publishing.md)
for actual candidate validation and publication. Historical failure-reproduction
timestamps, run IDs, and test counts belong in separate evidence records, not
as fixed rules in this procedure.
