"""Supported pure projection of already authorized social relationship facts.

Input: an immutable SocialContextItem supplied by the scoped reader.
Output: the existing social-context.v1 row and canonical fact digest.
No DB reads, permissions, commits, provider calls, or new serialization rules.
"""
from app.domains.relationships.contracts.social_context import SocialContextItem
from app.domains.relationships.policies.social_context_validation import facts_digest, social_context_row


def project_social_context_evidence(item: SocialContextItem) -> tuple[dict, str]:
    """Preserve the owner's exact validation and UTC digest before delivery."""
    digest = facts_digest(item)
    return social_context_row(item), digest
