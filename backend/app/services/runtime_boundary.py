"""Existing external extension import contract; implementation and state live in runtime.

Current Angmoo code imports the owner directly. Keep these same-object exports
while the independently deployed hosted extension uses its version-2 imports.
"""

from app.runtime.extensions.resident_adapter import (
    ResidentRuntimeError,
    ResidentRuntimeAuthError,
    ResidentRuntimeUnavailableError,
    ResidentRuntimeRegistrationError,
    OpenClawGatewayError,
    OpenClawGatewayAuthError,
    ResidentRuntimeAdapter,
    register_resident_runtime_adapter,
    unregister_resident_runtime_adapter,
    get_resident_runtime_adapter,
    OpenClawGatewayClient,
    openclaw_auth_profiles,
)

__all__ = ['ResidentRuntimeError', 'ResidentRuntimeAuthError', 'ResidentRuntimeUnavailableError', 'ResidentRuntimeRegistrationError', 'OpenClawGatewayError', 'OpenClawGatewayAuthError', 'ResidentRuntimeAdapter', 'register_resident_runtime_adapter', 'unregister_resident_runtime_adapter', 'get_resident_runtime_adapter', 'OpenClawGatewayClient', 'openclaw_auth_profiles']
