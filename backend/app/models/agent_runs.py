from app.domains.memory.models.daypart import AgentDaypartMemoryEvent  # noqa: F401
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


from app.domains.relationships.models.points import AgentRelationshipPoint
from app.domains.memory.models.daypart import AgentDaypartMemoryEvent
