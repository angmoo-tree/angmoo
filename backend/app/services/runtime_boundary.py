from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class ResidentRuntimeError(Exception):
    def __init__(
        self, message: str, *, diagnostics: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class ResidentRuntimeAuthError(ResidentRuntimeError):
    pass


class ResidentRuntimeUnavailableError(ResidentRuntimeError):
    pass


class ResidentRuntimeRegistrationError(ResidentRuntimeError):
    pass


# Compatibility names are intentionally kept while API and service callers move
# to the runtime-neutral error contract.
OpenClawGatewayError = ResidentRuntimeError
OpenClawGatewayAuthError = ResidentRuntimeAuthError


@runtime_checkable
class ResidentRuntimeAdapter(Protocol):
    name: str

    def create_gateway_client(self, *args: Any, **kwargs: Any) -> Any: ...

    def get_auth_profiles(self) -> Any: ...


_resident_runtime_adapter: ResidentRuntimeAdapter | None = None


def register_resident_runtime_adapter(adapter: ResidentRuntimeAdapter) -> None:
    global _resident_runtime_adapter
    if _resident_runtime_adapter is not None:
        raise ResidentRuntimeRegistrationError(
            "resident runtime adapter is already registered",
            diagnostics={"registered": _resident_runtime_adapter.name},
        )
    if (
        not isinstance(adapter, ResidentRuntimeAdapter)
        or not adapter.name.strip()
    ):
        raise ResidentRuntimeRegistrationError(
            "invalid resident runtime adapter"
        )
    _resident_runtime_adapter = adapter


def unregister_resident_runtime_adapter(
    adapter: ResidentRuntimeAdapter,
) -> None:
    global _resident_runtime_adapter
    if _resident_runtime_adapter is not adapter:
        raise ResidentRuntimeRegistrationError(
            "resident runtime adapter registration mismatch"
        )
    _resident_runtime_adapter = None


def get_resident_runtime_adapter() -> ResidentRuntimeAdapter | None:
    return _resident_runtime_adapter


def _require_resident_runtime_adapter() -> ResidentRuntimeAdapter:
    adapter = _resident_runtime_adapter
    if adapter is None:
        raise ResidentRuntimeUnavailableError(
            "resident runtime adapter is unavailable",
            diagnostics={"engine": "openclaw"},
        )
    return adapter


class OpenClawGatewayClient:
    """Compatibility constructor backed by an explicitly registered adapter."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        return _require_resident_runtime_adapter().create_gateway_client(
            *args,
            **kwargs,
        )


class _RegisteredAuthProfiles:
    def __getattr__(self, name: str) -> Any:
        profiles = _require_resident_runtime_adapter().get_auth_profiles()
        return getattr(profiles, name)


openclaw_auth_profiles = _RegisteredAuthProfiles()
