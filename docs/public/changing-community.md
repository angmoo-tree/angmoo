# Changing community behavior

Community contracts cover posts, replies, likes, reposts, follows,
notifications, state, pagination, and ownership.

Use transactions for multi-row writes. Test both the owner and a second
synthetic user for object access. Preserve reply semantics at `/replies`; the
legacy `/comments` behavior is not the write contract.

Changes to moderation, privacy, ownership, or deletion require hosted
validation.
