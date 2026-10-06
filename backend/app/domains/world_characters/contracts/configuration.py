"""Read-only effective values accepted by Chat, Social and Routine adapters."""
from dataclasses import dataclass
from app.domains.characters.service.import_configuration import ImportProfile, ImportSettings


@dataclass(frozen=True)
class WorldEffectiveConfiguration:
    world_id: str
    world_character_id: str
    character_id: str
    revision: int
    autonomous_enabled: bool
    profile: ImportProfile
    settings: ImportSettings

    def request_snapshot(self):
        return {"contract_version": "world-effective-configuration-v1", "world_id": self.world_id,
            "world_character_id": self.world_character_id, "character_id": self.character_id,
            "revision": self.revision, "autonomous_enabled": self.autonomous_enabled,
            "profile": self.profile.model_dump(mode="json"), "settings": self.settings.model_dump(mode="json")}


def configuration_from_request(data):
    if data.get("contract_version") != "world-effective-configuration-v1":
        raise ValueError("world_configuration_snapshot_invalid")
    return WorldEffectiveConfiguration(world_id=data["world_id"], world_character_id=data["world_character_id"],
        character_id=data["character_id"], revision=int(data["revision"]), autonomous_enabled=bool(data["autonomous_enabled"]),
        profile=ImportProfile.model_validate(data["profile"]), settings=ImportSettings.model_validate(data["settings"]))
