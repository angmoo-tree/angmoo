"""Inspect registered ORM structure only; never open an application database."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models import Base
from app.runtime.persistence.model_registration import register_models


def inventory() -> dict:
    metadata = register_models()
    owners = {mapper.local_table.name: mapper.class_.__module__ for mapper in Base.registry.mappers}
    return {"schema_version": 1, "source": "registered ORM metadata; no database opened",
        "tables": [{"name": table.name, "owner": owners.get(table.name),
            "primary_key": [column.name for column in table.primary_key],
            "columns": [{"name": column.name, "type": str(column.type), "nullable": column.nullable}
                for column in table.columns],
            "foreign_keys": [{"columns": [element.parent.name for element in constraint.elements],
                "target_table": constraint.referred_table.name,
                "target_columns": [element.column.name for element in constraint.elements],
                "ondelete": constraint.ondelete} for constraint in table.foreign_key_constraints]}
            for table in sorted(metadata.tables.values(), key=lambda item: item.name)]}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    body = json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n"
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        print(f"ORM dependency inventory saved: {target}")
    else:
        print(body)
