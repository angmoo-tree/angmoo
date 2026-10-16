# Pinned Vec1 build input

`vec1.c` is the unmodified public-domain SQLite Vec1 source already used by
Angmoo. Its original public-domain dedication remains at the top of the file.

- Upstream: https://sqlite.org/vec1/
- Original revision: `8fc7b115a4`
- Original source URL: https://sqlite.org/vec1/raw/vec1.c?ci=8fc7b115a4
- SHA-256: `8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86`
- Recovery evidence: PR #382 Core CI run `38924731687`, attempt 1,
  `vec1-sources-ecb42e4aee293a245b804e0aa93c047ccf224f7b-1` artifact.

On 2026-10-17 KST the original endpoint returned HTTP 500 on the Windows runner;
a subsequent direct check redirected to `https://sqlite.org/vec1.html`, returning
HTML instead of source. The existing checksum correctly rejected that response.
This copy was recovered from the successful same-attempt Core preflight artifact
and independently matched the existing source-controlled SHA-256. No dependency
version or source digest changed.

`scripts/build_vec1.py` verifies this digest on every use and also verifies any
cache hit. Missing or modified source fails closed. SQLite headers retain their
separate pinned official archive and hash. Windows and Linux compile their own
native binary; this directory contains no prebuilt binary. Git preserves exact
bytes across Windows checkouts, including upstream trailing whitespace (only
those formatting checks are disabled for this exact file), and the Docker build
copies the same source. The source digest, conflict-marker and security checks
remain active.

Any future Vec1 update must review source provenance, native compatibility and
the new digest together. Do not replace the checksum to accept an error page.
