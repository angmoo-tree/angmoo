"""An existing extension and the current runtime share one registration state."""

import pytest

from app.runtime.extensions import hosted_configuration as hosted
from app.runtime.extensions import resident_adapter as resident
from app.services import hosted_configuration as previous_hosted
from app.services import runtime_boundary as previous_resident


def test_previous_hosted_extension_registration_uses_current_runtime_state():
    class Settings:
        name = 'test-extension-settings'

        def get_setting(self, key):
            return 'registered-value' if key == 'example' else None

    class Prompts:
        name = 'test-extension-prompts'

        def get_prompt(self, key):
            return 'registered-prompt' if key == 'example' else None

    settings, prompts = Settings(), Prompts()
    assert previous_hosted.HostedSettingsProvider is hosted.HostedSettingsProvider
    assert previous_hosted.HostedPromptProvider is hosted.HostedPromptProvider
    assert previous_hosted.register_hosted_configuration is hosted.register_hosted_configuration
    previous_hosted.register_hosted_configuration(settings, prompts)
    try:
        assert hosted.get_hosted_setting('example') == 'registered-value'
        assert previous_hosted.get_hosted_prompt('example') == 'registered-prompt'
        with pytest.raises(hosted.HostedConfigurationRegistrationError, match='already registered'):
            hosted.register_hosted_configuration(settings, prompts)
    finally:
        hosted.unregister_hosted_configuration(settings, prompts)
    assert previous_hosted.get_hosted_setting('example') is None
    assert hosted.get_hosted_prompt('example') is None


def test_previous_resident_extension_registration_uses_current_runtime_state():
    client, profiles = object(), object()

    class Adapter:
        name = 'test-resident-extension'

        def create_gateway_client(self, *args, **kwargs):
            return client

        def get_auth_profiles(self):
            return profiles

    adapter = Adapter()
    assert previous_resident.ResidentRuntimeAdapter is resident.ResidentRuntimeAdapter
    assert previous_resident.openclaw_auth_profiles is resident.openclaw_auth_profiles
    previous_resident.register_resident_runtime_adapter(adapter)
    try:
        assert resident.get_resident_runtime_adapter() is adapter
        assert resident.OpenClawGatewayClient() is client
        assert previous_resident.OpenClawGatewayClient() is client
        with pytest.raises(resident.ResidentRuntimeRegistrationError, match='already registered'):
            resident.register_resident_runtime_adapter(adapter)
    finally:
        resident.unregister_resident_runtime_adapter(adapter)
    assert previous_resident.get_resident_runtime_adapter() is None
    with pytest.raises(previous_resident.ResidentRuntimeUnavailableError):
        resident.OpenClawGatewayClient()
