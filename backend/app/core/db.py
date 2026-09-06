"""Same Base for immutable migration sources; active code uses app.models."""

from app.models import Base

__all__ = ["Base"]
