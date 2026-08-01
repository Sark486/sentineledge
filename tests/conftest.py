"""Global test configuration.

Settings are read at import time by `app.core.config`, and `app.infrastructure.db`
builds an engine from them as a side effect of import. Pinning the values here —
before any `app.*` module is imported — keeps the suite independent of whatever
`.env` the developer happens to have. Nothing in the suite opens a connection.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
os.environ["MQTT_HOST"] = "test-broker"
