"""Developer-only compiler for reviewed, frozen owner erasure inventories.

Runtime loads the checked-in policies; it never guesses scope from schema changes.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/verification/world-deletion-orm-inventory-20261012.json"
PRESERVE = {"worlds", "owner_default_worlds", "characters", "character_import_snapshots", "character_import_origins",
    "character_card_sources", "world_package_sources", "world_package_exports", "agent_slots"}
DIRECT = {"agent_creation_drafts": "target_world_id", "world_package_imports": "imported_world_id"}
OWNING_PARENT = {"memory_hot_brief_items": "memory_hot_briefs", "memory_episode_unit_evidence": "memory_episode_units",
    "memory_item_evidence": "memory_items", "memory_situation_sources": "memory_items"}


def main():
    tables = {row["name"]: row for row in json.loads(INVENTORY.read_text(encoding="utf-8"))["tables"]}
    rules = {}
    for name, table in tables.items():
        if name in PRESERVE:
            continue
        columns = {column["name"] for column in table["columns"]}
        if "world_id" in columns or name in DIRECT:
            rules[name] = {"world_column": DIRECT.get(name, "world_id")}
    rules["agent_runs"] = {"special": "run_world"}
    rules["media_assets"] = {"special": "media_scope"}
    rules["world_package_imports"]["preserve_lineage"] = True
    changed = True
    while changed:
        changed = False
        for name, table in tables.items():
            if name in rules or name in PRESERVE:
                continue
            if name in OWNING_PARENT and OWNING_PARENT[name] not in rules:
                continue
            joins = [fk for fk in table["foreign_keys"] if fk["target_table"] in rules and fk["target_table"] != name]
            if name in OWNING_PARENT:
                joins = [fk for fk in joins if fk["target_table"] == OWNING_PARENT[name]]
            if joins:
                rules[name] = {"joins": [{key: fk[key] for key in ("columns", "target_table", "target_columns")} for fk in joins]}
                changed = True
    # No global Character ownership is inferred from an actor in one World.
    owners = {}
    for name, rule in sorted(rules.items()):
        owner = tables[name]["owner"].split(".")[2]
        owners.setdefault(owner, {})[name] = rule
    for owner, items in owners.items():
        path = ROOT / "backend/app/domains" / owner / "repository/world_erasure.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "owner": owner, "tables": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scoped_tables": len(rules), "owners": list(owners), "preserved": sorted(PRESERVE)}))


if __name__ == "__main__":
    main()
