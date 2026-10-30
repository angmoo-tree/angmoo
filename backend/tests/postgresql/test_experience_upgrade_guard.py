"""Offline upgrade must reject non-clone identities before opening a socket."""
import pytest
from app.runtime import postgresql_experience_upgrade as module


@pytest.mark.parametrize('dsn,database',[
    ('postgresql://angmoo_pg_run01_admin:synthetic@127.0.0.1:15414/angmoo_pg_run01','angmoo_pg_run01'),
    ('postgresql://angmoo_pg_run01_admin:synthetic@127.0.0.1:15414/angmoo_pg_run01_load_preserved','angmoo_pg_run01_load_preserved'),
    ('postgresql://angmoo_pg_run01_admin:synthetic@external.example:15414/angmoo_pg_run01_restore','angmoo_pg_run01_restore'),
    ('postgresql://angmoo_pg_run01_runtime:synthetic@127.0.0.1:15414/angmoo_pg_run01_restore','angmoo_pg_run01_restore'),
    ('postgresql://angmoo_pg_run01_admin:synthetic@127.0.0.1:5432/angmoo_pg_run01_restore','angmoo_pg_run01_restore'),
])
def test_only_explicit_loopback_experiment_clone_is_admitted(monkeypatch,dsn,database):
    def forbidden(*args,**kwargs):raise AssertionError('unexpected_database_connection')
    monkeypatch.setattr(module,'create_engine',forbidden)
    with pytest.raises(ValueError,match='snapshot_upgrade_requires_owned_clone'):
        module.upgrade(dsn,expected_database=database)
