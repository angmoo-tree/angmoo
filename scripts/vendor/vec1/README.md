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

## ARM64 compiler compatibility (2026-10-18)

The original source above remains byte-for-byte unchanged. GCC 14 on ARM64
rejects four signed/unsigned NEON type mismatches in the 32-bit metadata filter.
`compiler_source` in `scripts/build_vec1.py` verifies the original SHA first,
then applies `angmoo-neon-signed-mask-v1` with exact occurrence checks: signed
operands use `vceqq_s32`, and unsigned comparison masks use `vorrq_u32`.
The ARM64 build compiles and executes a scalar-versus-NEON comparison for all
six filter operators, negative/null values, complete SIMD blocks and tails.
The receipt records both original and compiled source hashes and the patch ID.
Windows/amd64 source bytes and compilation flags are unchanged.

Reference: https://arm-software.github.io/acle/neon_intrinsics/advsimd.html

ARM64 GCC의 네 줄 타입 불일치만 빌드 임시 복사본에서 교정한다. 원본·해시
검증을 보존하고 필터 결과를 scalar 구현과 비교한다. SIMD 비활성화나
타입 검사를 완화하는 컴파일 옵션은 사용하지 않는다.
