from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.runtime.persistence.model_registration import register_models
register_models()  # noqa: F401
from app.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # The v20 table rebuild must start with foreign keys disabled,
            # before the transaction. SQLite otherwise treats DDL as autocommit
            # and can leave a partially rebuilt table on a failed migration.
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        context.configure(connection=connection, target_metadata=target_metadata)
        try:
            with context.begin_transaction():
                context.run_migrations()
            if sqlite:
                connection.commit()
        except BaseException:
            if sqlite:
                connection.rollback()
            raise
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("sqlite_foreign_key_check_failed")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
