"""Exercise the installer's new-write probe against the actual target schema."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from app.domains.social.models.posts import Post
from app.runtime.postgresql_installation import private_file
from scripts.ci.run_windows_postgresql_qualification import check_pg


def test_installer_probe_writes_and_rereads_complete_post_rows(store, tmp_path):
    engine, _checkpoint, _scratch = store
    data = tmp_path / "qualified-installation"
    private_file(data / "postgresql-appdata/secrets/postgresql-runtime-dsn",
                 engine.url.render_as_string(hide_password=False).encode())
    with Session(engine) as session:
        session.add(Post(id="qualification-source", author_name="Synthetic fixture",
                         title="Before update", body="Preserved source post"))
        session.commit()
    written = check_pg(data, "qualification-source")
    second = check_pg(data, written)
    with Session(engine) as session:
        rows = {post.id: post for post in session.scalars(
            select(Post).where(Post.id.in_(["qualification-source", written, second]))
        )}
        assert set(rows) == {"qualification-source", written, second}
        assert rows["qualification-source"].body == "Preserved source post"
        assert rows[written].title and rows[written].body == "PostgreSQL 저장 검증"
