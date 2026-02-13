"""Pytest configuration and shared fixtures for tx2tx tests

This module provides common fixtures and test utilities used across
unit and integration tests.
"""

import pytest
import logging
from pathlib import Path
from typing import Generator

from tx2tx.common.config import Config, ConfigLoader
from tx2tx.common.settings import settings


@pytest.fixture(scope="session")
def test_config_path() -> Path:
    """Path to test configuration file"""
    return Path(__file__).parent / "test_config.yml"


@pytest.fixture
def sample_config() -> Config:
    """Load sample configuration for testing

    Returns:
        Config object with test values
    """
    config_path = Path(__file__).parent.parent / "config.yml"
    if not config_path.exists():
        pytest.skip("config.yml not found - required for this test")
    return ConfigLoader.config_load(config_path)


@pytest.fixture
def reset_settings() -> Generator[None, None, None]:
    """Reset settings singleton between tests

    This fixture ensures each test gets a fresh Settings instance.
    """
    # Reset singleton state
    settings._initialized = False
    settings._config = None
    yield
    # Cleanup after test
    settings._initialized = False
    settings._config = None


@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """Setup logging for tests"""
    caplog.set_level(logging.DEBUG)


# Markers for test organization
def pytest_configure(config) -> None:
    """Register custom pytest markers used by this test suite."""
    config.addinivalue_line("markers", "requires_x11: mark test as requiring X11 display")
