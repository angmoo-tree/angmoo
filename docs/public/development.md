# Contributor development

The supported contributor path is:

1. start PostgreSQL+pgvector with root `compose.yml`;
2. install locked backend and frontend dependencies;
3. apply every Alembic revision;
4. run `app.public_main:app`;
5. run the Next.js frontend;
6. validate with synthetic data and fake providers.

Copy the checked-in examples to `backend/.env` and `frontend/.env.local`.
Those local files are ignored and must never be committed.

The public profile requires LangGraph/direct and keeps the scheduler, image
worker, service image, and experimental image UI off. Do not place a real
provider key in contributor tests. Host-native PostgreSQL, alternative
container runtimes, and operating systems not covered by CI are best-effort.

Use `docker compose down` to stop the database. Add `--volumes` only when you
intentionally want to remove your local development data.
