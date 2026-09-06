"""Bind original nullable owner reads without changing the caller Session."""

from app.domains.characters.service import profile as character_profile
from app.domains.identity.service import profile as identity_profile
from app.domains.local_bot.contracts.authentication import (
    LocalBotAuthenticationWorkflows,
)


def build_authentication_workflows() -> LocalBotAuthenticationWorkflows:
    return LocalBotAuthenticationWorkflows(
        get_character=character_profile.get_character,
        get_user=identity_profile.get_user,
    )
