"""World Package import lifecycle and v1 trust labels."""

from enum import StrEnum


class WorldPackageImportState(StrEnum):
    RECEIVING = "RECEIVING"
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    PREVIEW_READY = "PREVIEW_READY"
    APPROVED = "APPROVED"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    DISCARDED = "DISCARDED"


class WorldPackageTrustState(StrEnum):
    LOCALLY_EXPORTED = "locally_exported"
    CHECKSUM_VERIFIED_UNSIGNED = "checksum_verified_unsigned"
