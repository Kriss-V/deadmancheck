import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock the database module before any app imports
sys.modules['app.database'] = MagicMock()

@pytest.fixture(autouse=True)
def mock_db():
    """Mock database connections for all tests"""
    with patch('app.database.get_db'):
        yield
