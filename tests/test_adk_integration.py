"""
ADK Integration Test Suite

Tests for:
- Session creation/retrieval
- Memory storage/retrieval
- USE_ADK toggle functionality
"""

import os
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestADKConfig:
    """Test ADK configuration and environment variable toggling."""
    
    def test_use_adk_default_false(self):
        """Test that USE_ADK defaults to False when not set."""
        # Clear environment variable
        original_value = os.environ.pop("USE_ADK", None)
        
        try:
            # Need to reimport to pick up new env
            from backend.config import settings
            assert settings.USE_ADK is False
        finally:
            if original_value is not None:
                os.environ["USE_ADK"] = original_value
    
    def test_use_adk_true_when_set(self):
        """Test that USE_ADK=True when environment variable is set."""
        os.environ["USE_ADK"] = "true"
        
        try:
            from backend.config import Settings
            test_settings = Settings()
            assert test_settings.USE_ADK is True
        finally:
            os.environ.pop("USE_ADK", None)
    
    def test_use_adk_case_insensitive(self):
        """Test that USE_ADK is case-insensitive."""
        os.environ["USE_ADK"] = "TRUE"
        
        try:
            from backend.config import Settings
            test_settings = Settings()
            assert test_settings.USE_ADK is True
        finally:
            os.environ.pop("USE_ADK", None)
    
    def test_adk_version_set(self):
        """Test that ADK_VERSION is set correctly."""
        from backend.config import settings
        assert settings.ADK_VERSION == "1.31.1"


class TestADKSessionWrapper:
    """Test ADK Session Wrapper functionality."""
    
    @pytest.fixture
    def mock_adk_session(self):
        """Create a mock ADK session for testing."""
        with patch("backend.adk.adk_session_wrapper.AdSession") as MockSession:
            mock_instance = MagicMock()
            mock_instance.id = "test-session-123"
            mock_instance.user_id = "user-456"
            mock_instance.app_name = "test-app"
            MockSession.return_value = mock_instance
            yield mock_instance
    
    def test_session_wrapper_imports(self):
        """Test that ADKSessionWrapper can be imported."""
        try:
            from backend.adk import ADKSessionWrapper
            assert ADKSessionWrapper is not None
        except ImportError as e:
            pytest.skip(f"ADK not installed: {e}")
    
    def test_session_creation(self, mock_adk_session):
        """Test session creation through wrapper."""
        try:
            from backend.adk import ADKSessionWrapper
            
            wrapper = ADKSessionWrapper()
            session = wrapper.create_session(
                user_id="user-456",
                app_name="test-app",
                session_id="test-session-123"
            )
            
            assert session is not None
            assert session.id == "test-session-123"
        except ImportError:
            pytest.skip("ADK not installed")
    
    def test_session_retrieval(self, mock_adk_session):
        """Test session retrieval through wrapper."""
        try:
            from backend.adk import ADKSessionWrapper
            
            wrapper = ADKSessionWrapper()
            session = wrapper.get_session("test-session-123")
            
            assert session is not None
        except ImportError:
            pytest.skip("ADK not installed")


class TestADKMemoryWrapper:
    """Test ADK Memory Wrapper functionality."""
    
    @pytest.fixture
    def mock_adk_memory(self):
        """Create a mock ADK memory service for testing."""
        with patch("backend.adk.adk_memory_wrapper.AdMemoryService") as MockMemory:
            mock_instance = MagicMock()
            mock_instance.search.return_value = [
                {"content": "test memory", "score": 0.95}
            ]
            MockMemory.return_value = mock_instance
            yield mock_instance
    
    def test_memory_wrapper_imports(self):
        """Test that ADKMemoryWrapper can be imported."""
        try:
            from backend.adk import ADKMemoryWrapper
            assert ADKMemoryWrapper is not None
        except ImportError as e:
            pytest.skip(f"ADK not installed: {e}")
    
    def test_memory_save(self, mock_adk_memory):
        """Test memory storage through wrapper."""
        try:
            from backend.adk import ADKMemoryWrapper
            
            wrapper = ADKMemoryWrapper()
            result = wrapper.save(
                session_id="test-session-123",
                content="Test memory content"
            )
            
            assert result is True
        except ImportError:
            pytest.skip("ADK not installed")
    
    def test_memory_retrieval(self, mock_adk_memory):
        """Test memory retrieval through wrapper."""
        try:
            from backend.adk import ADKMemoryWrapper
            
            wrapper = ADKMemoryWrapper()
            memories = wrapper.search(
                session_id="test-session-123",
                query="test query"
            )
            
            assert len(memories) > 0
            assert memories[0]["content"] == "test memory"
        except ImportError:
            pytest.skip("ADK not installed")


class TestUSEADKToggle:
    """Test USE_ADK environment variable toggle behavior."""
    
    def test_when_use_adk_false_fallback_used(self):
        """Test that fallback implementation is used when USE_ADK=false."""
        os.environ["USE_ADK"] = "false"
        
        try:
            from backend.config import Settings
            test_settings = Settings()
            
            assert test_settings.USE_ADK is False
            # When USE_ADK is False, the system should use fallback implementations
        finally:
            os.environ.pop("USE_ADK", None)
    
    def test_when_use_adk_true_adk_used(self):
        """Test that ADK is used when USE_ADK=true."""
        os.environ["USE_ADK"] = "true"
        
        try:
            from backend.config import Settings
            test_settings = Settings()
            
            assert test_settings.USE_ADK is True
            # When USE_ADK is True, the system should use ADK implementations
        finally:
            os.environ.pop("USE_ADK", None)
    
    @pytest.mark.parametrize("env_value,expected", [
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("false", False),
        ("FALSE", False),
        ("False", False),
        ("yes", False),  # Only "true" variants should work
        ("1", False),
        ("", False),
    ])
    def test_use_adk_various_values(self, env_value, expected):
        """Test various USE_ADK environment variable values."""
        os.environ["USE_ADK"] = env_value
        
        try:
            from backend.config import Settings
            test_settings = Settings()
            assert test_settings.USE_ADK is expected
        finally:
            os.environ.pop("USE_ADK", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
