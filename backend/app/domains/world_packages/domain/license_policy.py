"""Pure World Package v1 license validation and preview policy."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.manifest import WorldPackageLicense
from app.domains.world_packages.domain.package_policy import WorldPackagePolicy


SUPPORTED_LICENSE_EXPRESSIONS = frozenset(
    {
        "CC0-1.0",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "GPL-3.0-only",
        "LicenseRef-Angmoo-Private",
    }
)
_LICENSE_REF = re.compile(r"^LicenseRef-[A-Za-z0-9][A-Za-z0-9.-]{0,119}$")


@dataclass(frozen=True, slots=True)
class WorldPackageLicenseAssessment:
    custom_reference: bool
    local_only: bool
    warnings: tuple[str, ...]


def validate_world_package_license(
    license: WorldPackageLicense,
    license_text: str | None,
) -> WorldPackageLicenseAssessment:
    """Validate the frozen v1 expression without attempting legal inference."""

    expression = license.expression
    custom_reference = expression.startswith("LicenseRef-")
    if custom_reference:
        if _LICENSE_REF.fullmatch(expression) is None:
            raise WorldPackageContractError(
                WorldPackageReasonCode.LICENSE_MISSING
            )
        if license.license_text_path != "LICENSE.txt" or not license_text:
            raise WorldPackageContractError(
                WorldPackageReasonCode.LICENSE_MISSING
            )
    elif expression not in SUPPORTED_LICENSE_EXPRESSIONS:
        raise WorldPackageContractError(WorldPackageReasonCode.LICENSE_MISSING)

    if not custom_reference and (
        license.license_text_path is not None or license_text is not None
    ):
        raise WorldPackageContractError(WorldPackageReasonCode.ARCHIVE_INVALID)
    if license_text is not None:
        try:
            encoded = license_text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.LICENSE_MISSING
            ) from exc
        if (
            not encoded
            or len(encoded) > WorldPackagePolicy.MAX_LICENSE_TEXT_BYTES
            or "\x00" in license_text
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
            )

    local_only = expression == "LicenseRef-Angmoo-Private"
    warnings: list[str] = []
    if custom_reference and not local_only:
        warnings.append("custom_license_review_required")
    if local_only:
        warnings.append("local_only_license")
    return WorldPackageLicenseAssessment(
        custom_reference=custom_reference,
        local_only=local_only,
        warnings=tuple(warnings),
    )


__all__ = [
    "SUPPORTED_LICENSE_EXPRESSIONS",
    "WorldPackageLicenseAssessment",
    "validate_world_package_license",
]
