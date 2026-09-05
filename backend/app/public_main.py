"""Temporary G06 import compatibility; the app implementation lives in main.

Existing callers retain the public health and no-default-component contracts.
The remaining launcher/ASGI/test references retire in AR-B8-A/B, after their
specific contracts and fresh bundle loading are verified.
"""

from app.main import (
    HostedBackendExtension,
    HostedExtensionConfigurationError,
    HostedLifecycleHook,
    LifespanHandler,
    PublicRuntimeConfigurationError,
    Settings,
    health,
    main,
    runtime_health,
    settings,
    validate_public_runtime_settings,
)
from app.main import (
    create_public_app as create_app,
)
from app.main import (
    create_public_lifespan as create_lifespan,
)
from app.main import (
    public_app as app,
)
from app.main import (
    public_lifespan as lifespan,
)

__all__ = [
    "HostedBackendExtension",
    "HostedExtensionConfigurationError",
    "HostedLifecycleHook",
    "LifespanHandler",
    "PublicRuntimeConfigurationError",
    "Settings",
    "create_app",
    "create_lifespan",
    "health",
    "main",
    "app",
    "lifespan",
    "runtime_health",
    "settings",
    "validate_public_runtime_settings",
]

if __name__ == "__main__":
    main()
