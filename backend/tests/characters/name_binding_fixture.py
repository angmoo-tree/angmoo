"""Local fixture setup uses the real My Profile API; production resolution is read-only."""
from datetime import UTC, datetime
from app.domains.identity.models import InstallationIdentity
from app.domains.world_characters.contracts.owner_identity import OwnerControlledProfile
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.worlds.models import WorldMembership
from sqlalchemy import select


def create_profile(db, world, owner_id, name="민식"):
    if db.get(InstallationIdentity, "local-installation") is None:
        db.add(InstallationIdentity(singleton_key="local-installation", installation_id="names-test",
            owner_user_id=owner_id, bootstrap_state="claimed", local_label="test", claimed_at=datetime.now(UTC)))
    world.owner_user_id = owner_id
    membership = db.scalar(select(WorldMembership).where(WorldMembership.world_id == world.id, WorldMembership.user_id == owner_id))
    membership.role = "owner"
    db.commit()
    return OwnerControlledIdentityService(db).create(world_id=world.id, current_user_id=owner_id,
        profile=OwnerControlledProfile(name, None, "", None, "", (), ""))


def rename_profile(db, world_id, owner_id, name):
    from app.domains.world_characters.schemas.identity import MyProfilePatch
    service = OwnerControlledIdentityService(db)
    current = service.get(world_id=world_id, current_user_id=owner_id)
    return service.patch(world_id=world_id, current_user_id=owner_id,
        data=MyProfilePatch(version=current.version, display_name=name))
