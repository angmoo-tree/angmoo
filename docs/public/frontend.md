# Frontend guide

The frontend is a Next.js application. Backend calls belong in `src/lib`; UI
components should not duplicate REST contracts.

`ANGMOO_API_BASE_URL` points server-side proxy routes at the local FastAPI
process. `NEXT_PUBLIC_EXPERIMENTAL_IMAGE_ENABLED` is `false` by default.
Turning it on exposes the experimental image controls but does not enable the
backend worker or supply provider credentials.

The public build uses the system font stack and must succeed without a remote
font download. New default assets must be tracked, rights-cleared, and added to
the exporter and asset manifest.
