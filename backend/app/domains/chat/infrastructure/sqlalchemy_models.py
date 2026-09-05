"""Frozen migration compatibility: the canonical Chat model module is identical."""
import sys
from app.domains.chat import models

sys.modules[__name__] = models
