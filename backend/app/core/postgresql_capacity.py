"""Connection budget for one isolated Angmoo PostgreSQL backend process."""
from dataclasses import dataclass

MAIN_POOL_SIZE = 10
MAIN_POOL_OVERFLOW = 5
CHECKPOINT_POOL_MAX = 2
DIRECT_CONNECTION_MAX = 2
RUNTIME_CONNECTION_LIMIT = 20  # Main 15 + checkpoints 2 + direct 2 + transition 1.
SERVER_CONNECTION_LIMIT = 28  # Runtime 20 + operators 2 + reserved 3 + headroom 3.
SUPERUSER_RESERVED_CONNECTIONS = 3


@dataclass(frozen=True)
class PostgresPoolSettings:
    size: int = MAIN_POOL_SIZE
    overflow: int = MAIN_POOL_OVERFLOW
    timeout: float = 0.25

    def __post_init__(self):
        if self.size < 1 or self.overflow < 0 or self.timeout <= 0:
            raise ValueError('postgresql_pool_configuration_invalid')
        if (self.size + self.overflow + CHECKPOINT_POOL_MAX + DIRECT_CONNECTION_MAX
                >= RUNTIME_CONNECTION_LIMIT):
            raise ValueError('postgresql_pool_exceeds_runtime_budget')
