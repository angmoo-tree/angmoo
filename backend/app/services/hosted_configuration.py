"""Existing external extension import contract; implementation and state live in runtime.

Current Angmoo code imports the owner directly. Keep these same-object exports
while the independently deployed hosted extension uses its version-2 imports.
"""

from app.runtime.extensions.hosted_configuration import (
    HOSTED_EXTENSION_CONTRACT_VERSION,
    HostedSettingValue,
    HostedConfigurationRegistrationError,
    HostedSettingsProvider,
    HostedPromptProvider,
    validate_hosted_configuration_providers,
    register_hosted_configuration,
    unregister_hosted_configuration,
    get_hosted_setting,
    get_hosted_prompt,
)

__all__ = ['HOSTED_EXTENSION_CONTRACT_VERSION', 'HostedSettingValue', 'HostedConfigurationRegistrationError', 'HostedSettingsProvider', 'HostedPromptProvider', 'validate_hosted_configuration_providers', 'register_hosted_configuration', 'unregister_hosted_configuration', 'get_hosted_setting', 'get_hosted_prompt']
