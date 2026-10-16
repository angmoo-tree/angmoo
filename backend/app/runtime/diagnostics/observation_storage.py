"""Recorder file paths and atomic JSON replacement, independent of observers."""
import json
import os
from pathlib import Path
import re
from time import sleep
from uuid import uuid4


_SESSION = re.compile(r"sns-[0-9a-f]{32}\Z")


def observation_root(data_root: Path) -> Path:
    return data_root.resolve() / "diagnostics" / "sns"


def session_path(data_root: Path, session_id: str) -> Path:
    if not _SESSION.fullmatch(session_id):
        raise ValueError("sns_session_id_invalid")
    return observation_root(data_root) / session_id


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows can temporarily deny replacement while a recorder
                # thread has the old manifest open. Keep the operation atomic.
                if os.name != "nt" or attempt == 4:
                    raise
                sleep(0.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)
