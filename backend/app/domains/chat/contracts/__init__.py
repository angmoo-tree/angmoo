"""Chat thread model-binding contracts shared by storage and HTTP."""
from app.domains.chat.contracts.model_binding import (
    MESSAGE_MODEL_BINDING_MODES,
    MessageModelBindingMode,
)

__all__ = ["MESSAGE_MODEL_BINDING_MODES", "MessageModelBindingMode"]
