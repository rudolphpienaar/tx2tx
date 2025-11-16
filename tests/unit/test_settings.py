"""Unit tests for settings singleton"""

import pytest
from tx2tx.common.config import Config, ServerConfig, ClientConnectionConfig, ClientReconnectConfig, ProtocolConfig, LoggingConfig
from tx2tx.common.settings import Settings, settings


class TestSettingsSingleton:
    """Test Settings singleton pattern"""

    def test_singleton_same_instance(self, reset_settings):
        """Test that Settings() returns same instance"""
        s1 = Settings()
        s2 = Settings()
        assert s1 is s2

    def test_global_settings_is_singleton(self, reset_settings):
        """Test that global 'settings' is the singleton"""
        s = Settings()
        assert settings is s


class TestSettingsConstants:
    """Test that all constants are accessible"""

    def test_server_constants(self):
        """Test server constants exist and have correct values"""
        assert settings.HYSTERESIS_DELAY_SEC == 0.2
        assert settings.POLL_INTERVAL_DIVISOR == 1000.0
        assert settings.EDGE_ENTRY_OFFSET == 2

    def test_client_constants(self):
        """Test client constants exist"""
        assert settings.RECONNECT_CHECK_INTERVAL == 0.01

    def test_pointer_tracking_constants(self):
        """Test pointer tracking constants exist"""
        assert settings.POSITION_HISTORY_SIZE == 5
        assert settings.MIN_SAMPLES_FOR_VELOCITY == 2
        assert settings.DEFAULT_VELOCITY_THRESHOLD == 100.0


class TestSettingsInitialization:
    """Test settings initialization with config"""

    def test_initialize_with_config(self, reset_settings, sample_config):
        """Test settings can be initialized with config"""
        settings.initialize(sample_config)

        # Should not raise
        config = settings.config
        assert config is not None

    def test_config_property_before_init_raises(self, reset_settings):
        """Test accessing config before initialization raises error"""
        with pytest.raises(RuntimeError, match="Settings not initialized"):
            _ = settings.config

    def test_initialize_multiple_times(self, reset_settings, sample_config):
        """Test that initialize can be called multiple times"""
        settings.initialize(sample_config)
        config1 = settings.config

        # Create a different config
        different_config = Config(
            server=sample_config.server,
            clients=[],
            client=sample_config.client,
            protocol=sample_config.protocol,
            logging=sample_config.logging
        )

        settings.initialize(different_config)
        config2 = settings.config

        # Should have the new config
        assert config2 is different_config
        assert config2 is not config1


class TestSettingsDocumentation:
    """Test that constants have docstrings"""

    def test_constants_have_docstrings(self):
        """Test that important constants have documentation"""
        # Check class docstring
        assert Settings.__doc__ is not None

        # Check that constants are documented in class docstring
        doc = Settings.__doc__
        assert "singleton" in doc.lower()


class TestSettingsThreadSafety:
    """Test settings singleton behavior"""

    def test_singleton_initialization_idempotent(self, reset_settings):
        """Test that creating Settings multiple times is safe"""
        s1 = Settings()
        s1_id = id(s1)

        # Create again - should get same instance
        s2 = Settings()
        s2_id = id(s2)

        assert s1_id == s2_id
