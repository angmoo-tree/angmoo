"""Package trust, duplicate/tamper and collision decisions over read-only facts.

Collision facts cover the installation, not just the importing owner's rows.
A matching locally exported digest proves local provenance, not author identity.
"""
from app.domains.world_packages.policies.collision import WorldPackageDuplicateState, plan_world_package_collisions
from app.domains.world_packages.exceptions import WorldPackageContractError, WorldPackageReasonCode
from app.domains.world_packages.constants import WorldPackageTrustState
from app.domains.world_packages.contracts.preview import ValidatedWorldPackage, WorldPackagePreviewAssessment


def assess_world_package_preview(
    *, package: ValidatedWorldPackage, locally_exported: bool,
    imports: tuple[tuple[int, str], ...], world_slugs: frozenset[str], handles: frozenset[str],
) -> WorldPackagePreviewAssessment:
    manifest = package.manifest
    trust_state = (
        WorldPackageTrustState.LOCALLY_EXPORTED
        if locally_exported
        else WorldPackageTrustState.CHECKSUM_VERIFIED_UNSIGNED
    )

    same_version = tuple(
        item
        for item in imports
        if item[0] == manifest.package_version
    )
    if any(
        item[1] != manifest.content_digest
        for item in same_version
    ):
        raise WorldPackageContractError(
            WorldPackageReasonCode.TAMPERED_VERSION
        )
    if same_version:
        duplicate_state = WorldPackageDuplicateState.ALREADY_IMPORTED
    elif imports:
        duplicate_state = WorldPackageDuplicateState.INDEPENDENT_FORK
    else:
        duplicate_state = WorldPackageDuplicateState.NEW_PACKAGE

    collision_plan = plan_world_package_collisions(
        world_name=package.world.name,
        character_hints=tuple(
            (item.ref, item.display_name, item.handle_hint)
            for item in package.characters.characters
        ),
        content_digest=manifest.content_digest,
        existing_world_slugs=world_slugs,
        existing_character_handles=handles,
        duplicate_state=duplicate_state,
    )
    warnings = ["author_signature_not_available"]
    if duplicate_state is WorldPackageDuplicateState.ALREADY_IMPORTED:
        warnings.append("already_imported")
    elif duplicate_state is WorldPackageDuplicateState.INDEPENDENT_FORK:
        warnings.append("independent_fork_no_merge")
    return WorldPackagePreviewAssessment(
        trust_state=trust_state,
        collision_plan=collision_plan,
        warnings=tuple(warnings),
    )
