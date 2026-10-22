"""Compose the required default-space initializer at the HTTP boundary."""

from app.runtime.relationships.policy_activation import initialize_default_space_policy


def default_space_initializer():
    return initialize_default_space_policy
