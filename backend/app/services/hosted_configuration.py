from __future__ import annotations

from typing import Protocol, TypeAlias, runtime_checkable


HOSTED_EXTENSION_CONTRACT_VERSION = 2

HostedSettingValue: TypeAlias = (
    str | int | float | bool | tuple[str, ...] | None
)


class HostedConfigurationRegistrationError(RuntimeError):
    pass


@runtime_checkable
class HostedSettingsProvider(Protocol):
    name: str

    def get_setting(self, key: str) -> HostedSettingValue: ...


@runtime_checkable
class HostedPromptProvider(Protocol):
    name: str

    def get_prompt(self, key: str) -> str | None: ...


class _PublicHostedSettingsProvider:
    name = "public-default"

    def get_setting(self, key: str) -> HostedSettingValue:
        return None


class _PublicHostedPromptProvider:
    name = "public-default"

    def get_prompt(self, key: str) -> str | None:
        return None


_public_settings_provider: HostedSettingsProvider = (
    _PublicHostedSettingsProvider()
)
_public_prompt_provider: HostedPromptProvider = _PublicHostedPromptProvider()
_settings_provider: HostedSettingsProvider = _public_settings_provider
_prompt_provider: HostedPromptProvider = _public_prompt_provider


def validate_hosted_configuration_providers(
    settings_provider: HostedSettingsProvider,
    prompt_provider: HostedPromptProvider,
) -> None:
    if (
        not isinstance(settings_provider, HostedSettingsProvider)
        or not settings_provider.name.strip()
    ):
        raise HostedConfigurationRegistrationError(
            "invalid hosted settings provider"
        )
    if (
        not isinstance(prompt_provider, HostedPromptProvider)
        or not prompt_provider.name.strip()
    ):
        raise HostedConfigurationRegistrationError(
            "invalid hosted prompt provider"
        )


def register_hosted_configuration(
    settings_provider: HostedSettingsProvider,
    prompt_provider: HostedPromptProvider,
) -> None:
    global _settings_provider, _prompt_provider
    validate_hosted_configuration_providers(
        settings_provider,
        prompt_provider,
    )
    if (
        _settings_provider is not _public_settings_provider
        or _prompt_provider is not _public_prompt_provider
    ):
        raise HostedConfigurationRegistrationError(
            "hosted configuration is already registered"
        )
    _settings_provider = settings_provider
    _prompt_provider = prompt_provider


def unregister_hosted_configuration(
    settings_provider: HostedSettingsProvider,
    prompt_provider: HostedPromptProvider,
) -> None:
    global _settings_provider, _prompt_provider
    if (
        _settings_provider is not settings_provider
        or _prompt_provider is not prompt_provider
    ):
        raise HostedConfigurationRegistrationError(
            "hosted configuration registration mismatch"
        )
    _settings_provider = _public_settings_provider
    _prompt_provider = _public_prompt_provider


def get_hosted_setting(key: str) -> HostedSettingValue:
    return _settings_provider.get_setting(key)


def get_hosted_prompt(key: str) -> str | None:
    return _prompt_provider.get_prompt(key)
