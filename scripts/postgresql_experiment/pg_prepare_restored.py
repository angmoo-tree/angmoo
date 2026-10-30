import json
from pathlib import Path
from app.runtime.postgresql_migration import Migration
from app.runtime.postgresql_backend import install_validation_guards

install_validation_guards()
m=Migration(Path('/experiment/migration'),Path('/experiment/secrets/restore-dsn').read_text().strip())
try:print(json.dumps(m.prepare_appdata(Path('/experiment/appdata-restore'))))
finally:m.engine.dispose()
