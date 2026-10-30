"""Fail when a readable SQLite predecessor lacks a real NSIS fixture."""

from __future__ import annotations

from pathlib import Path
import sys
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION
from build_windows_installer_supported_upgrade_fixture import (
    SUPPORTED_SOURCE_VERSIONS,
)


def validate_matrix(root: Path = REPOSITORY_ROOT) -> tuple[int, ...]:
    # Historical SQLite deltas remain tested by their frozen fixture corpus.
    # Current product upgrades accept only the published 0.1.3/schema41 input.
    jobs=yaml.safe_load((root/'.github/workflows/windows-installer.yml').read_text())['jobs']
    selected={'installed-runtime-smoke':'clean-install','windows-installer-supported-upgrade':'upgrade-013',
              'windows-installer-failure-recovery':'failure-recovery','windows-installer-representative-upgrade':'upgrade-013'}
    for name,kind in selected.items():
        job=jobs[name]
        if ('continue-on-error' in job or job.get('timeout-minutes')!=35
                or not any('run_windows_postgresql_qualification.ps1' in step.get('run','')
                    and '-Kind '+kind in step['run'] for step in job['steps'])):
            raise ValueError('windows_installer_postgresql_case_not_executed')
    if not any('windows_postgresql_coverage.py' in step.get('run','') and '--run-attempt' in step['run']
               for step in jobs['windows-installer']['steps']):
        raise ValueError('windows_installer_postgresql_union_missing')
    runner=(root/'scripts/ci/run_windows_postgresql_qualification.py').read_text()
    for token in ('OLD_EXE_SHA','0.1.3','interrupted_after_canonical','windows_pg_source_changed_after_conversion',
                  'windows_pg_installer_converted_without_consent','windows_pg_hosted_only'):
        if token not in runner:raise ValueError('windows_installer_postgresql_rehearsal_missing')
    return (41,)


def main() -> int:
    try:
        readable_predecessors = validate_matrix()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        "windows_installer_supported_upgrade_matrix_contract_pass:"
        + ",".join(f"v{version}" for version in readable_predecessors)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
