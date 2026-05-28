import pytest
import sys
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

# Create a proper mock database module
mock_db_module = MagicMock()

# Create a proper async mock for get_db that returns something FastAPI can use
async def mock_get_db():
    yield MagicMock(spec=AsyncSession)

mock_db_module.get_db = mock_get_db
mock_db_module.Base = MagicMock()
mock_db_module.AsyncSessionLocal = MagicMock()
mock_db_module.engine = MagicMock()

# Mock it before any imports happen
sys.modules['app.database'] = mock_db_module

# Also mock the models that reference database
mock_models_module = MagicMock()
mock_models_module.Monitor = MagicMock()
mock_models_module.Ping = MagicMock()
mock_models_module.StatusPage = MagicMock()
mock_models_module.UptimeMonitor = MagicMock()
mock_models_module.User = MagicMock()
mock_models_module.UptimeCheck = MagicMock()
sys.modules['app.models'] = mock_models_module
sys.modules['app.models.monitor'] = MagicMock()
sys.modules['app.models.ping'] = MagicMock()
sys.modules['app.models.user'] = MagicMock()
sys.modules['app.models.uptime_monitor'] = MagicMock()
sys.modules['app.models.status_page'] = MagicMock()
