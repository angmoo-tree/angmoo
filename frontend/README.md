# Angmoo frontend

From this directory:

```bash
cp .env.example .env.local
pnpm install --frozen-lockfile
pnpm dev
```

The frontend proxies API requests to `ANGMOO_API_BASE_URL`. Experimental image
controls and private admin navigation are disabled in the public example.
