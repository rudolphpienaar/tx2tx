"""Unit tests for configuration loading and parsing"""

import pytest
from pathlib import Path
from tx2tx.common.config import (
    Config,
    ConfigLoader,
    ServerConfig,
    ClientReconnectConfig,
    NamedClientConfig,
    PanicKeyConfig,
)


class TestConfigLoaderYAMLLoading:
    """Test YAML file loading"""

    def test_yaml_load_valid_file(self, tmp_path):
        """Test loading valid YAML file"""
        config_file = tmp_path / "test.yml"
        config_file.write_text(
            """
server:
  host: "0.0.0.0"
  port: 25000
"""
        )

        data = ConfigLoader.yaml_load(config_file)
        assert isinstance(data, dict)
        assert "server" in data
        assert data["server"]["host"] == "0.0.0.0"

    def test_yaml_load_missing_file_raises(self):
        """Test loading non-existent file raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            ConfigLoader.yaml_load(Path("/nonexistent/config.yml"))

    def test_yaml_load_invalid_yaml_raises(self, tmp_path):
        """Test loading invalid YAML raises error"""
        config_file = tmp_path / "invalid.yml"
        config_file.write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(Exception):  # yaml.YAMLError or similar
            ConfigLoader.yaml_load(config_file)

    def test_yaml_load_non_dict_raises(self, tmp_path):
        """Test loading YAML that isn't a dict raises ValueError"""
        config_file = tmp_path / "list.yml"
        config_file.write_text("- item1\n- item2")

        with pytest.raises(ValueError, match="must contain a YAML dictionary"):
            ConfigLoader.yaml_load(config_file)


class TestConfigLoaderParsing:
    """Test configuration dictionary parsing"""

    def test_config_parse_minimal(self):
        """Test parsing minimal valid config"""
        data = {
            "server": {
                "host": "0.0.0.0",
                "port": 25000,
                "edge_threshold": 5,
                "poll_interval_ms": 10,
                "max_clients": 4,
            },
            "client": {
                "server_address": "server:25000",
                "reconnect": {
                    "enabled": True,
                    "max_attempts": 5,
                    "delay_seconds": 1.0,
                },
            },
            "protocol": {
                "version": "2.0.0",
                "buffer_size": 4096,
                "keepalive_interval": 30,
            },
            "logging": {
                "level": "INFO",
                "format": "%(message)s",
            },
        }

        config = ConfigLoader.config_parse(data)

        assert isinstance(config, Config)
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 25000
        assert config.client.server_address == "server:25000"
        assert config.protocol.version == "2.0.0"
        assert config.logging.level == "INFO"

    def test_config_parse_with_defaults(self):
        """Test parsing config with default values applied"""
        data = {
            "server": {
                "host": "0.0.0.0",
                "port": 25000,
                "edge_threshold": 5,
                "poll_interval_ms": 10,
                "max_clients": 4,
                # name, display, velocity_threshold, client_position omitted
            },
            "client": {
                "server_address": "server:25000",
                "reconnect": {
                    "enabled": True,
                    "max_attempts": 5,
                    "delay_seconds": 1.0,
                },
                # display omitted
            },
            "protocol": {
                "version": "2.0.0",
                "buffer_size": 4096,
                "keepalive_interval": 30,
            },
            "logging": {
                "level": "INFO",
                "format": "%(message)s",
                # file omitted
            },
        }

        config = ConfigLoader.config_parse(data)

        # Check defaults
        assert config.server.name == "TX2TX"
        assert config.server.display is None
        assert config.server.velocity_threshold == 100.0
        assert config.server.client_position == "west"
        assert config.client.display is None
        assert config.logging.file is None

    def test_config_parse_with_named_clients(self):
        """Test parsing config with named clients list"""
        data = {
            "server": {
                "host": "0.0.0.0",
                "port": 25000,
                "edge_threshold": 5,
                "poll_interval_ms": 10,
                "max_clients": 4,
            },
            "clients": [
                {"name": "laptop", "position": "west"},
                {"name": "desktop", "position": "east"},
            ],
            "client": {
                "server_address": "server:25000",
                "reconnect": {
                    "enabled": True,
                    "max_attempts": 5,
                    "delay_seconds": 1.0,
                },
            },
            "protocol": {
                "version": "2.0.0",
                "buffer_size": 4096,
                "keepalive_interval": 30,
            },
            "logging": {
                "level": "INFO",
                "format": "%(message)s",
            },
        }

        config = ConfigLoader.config_parse(data)

        assert len(config.clients) == 2
        assert config.clients[0].name == "laptop"
        assert config.clients[0].position == "west"
        assert config.clients[1].name == "desktop"
        assert config.clients[1].position == "east"

    def test_config_parse_missing_required_field_raises(self):
        """Test parsing config with missing required field raises KeyError"""
        data = {
            "server": {
                "host": "0.0.0.0",
                # port missing
                "edge_threshold": 5,
                "poll_interval_ms": 10,
                "max_clients": 4,
            },
            "client": {
                "server_address": "server:25000",
                "reconnect": {
                    "enabled": True,
                    "max_attempts": 5,
                    "delay_seconds": 1.0,
                },
            },
            "protocol": {
                "version": "2.0.0",
                "buffer_size": 4096,
                "keepalive_interval": 30,
            },
            "logging": {
                "level": "INFO",
                "format": "%(message)s",
            },
        }

        with pytest.raises(KeyError):
            ConfigLoader.config_parse(data)


class TestConfigLoaderFileFinding:
    """Test config file discovery"""

    def test_configFile_find_current_directory(self, tmp_path, monkeypatch):
        """Test finding config.yml in current directory"""
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yml"
        config_file.write_text("test: data")

        found = ConfigLoader.configFile_find()
        assert found == config_file.resolve()

    def test_configFile_find_returns_none_when_not_found(self, tmp_path, monkeypatch):
        """Test returns None when no config file found"""
        monkeypatch.chdir(tmp_path)
        found = ConfigLoader.configFile_find()
        assert found is None


class TestConfigLoaderFullLoad:
    """Test complete config loading"""

    def test_config_load_explicit_path(self, tmp_path):
        """Test loading config from explicit path"""
        config_file = tmp_path / "myconfig.yml"
        config_file.write_text(
            """
server:
  host: "0.0.0.0"
  port: 25000
  edge_threshold: 5
  poll_interval_ms: 10
  max_clients: 4

client:
  server_address: "server:25000"
  reconnect:
    enabled: true
    max_attempts: 5
    delay_seconds: 1.0

protocol:
  version: "2.0.0"
  buffer_size: 4096
  keepalive_interval: 30

logging:
  level: "INFO"
  format: "%(message)s"
"""
        )

        config = ConfigLoader.config_load(config_file)
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 25000

    def test_config_load_auto_discover_raises_when_not_found(self, tmp_path, monkeypatch):
        """Test auto-discovery raises FileNotFoundError when no config found"""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            ConfigLoader.config_load()


class TestConfigLoaderOverrides:
    """Test config loading with overrides"""

    def test_configWithOverrides_load_server_overrides(self, tmp_path):
        """Test applying server config overrides"""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
server:
  name: "OriginalName"
  host: "0.0.0.0"
  port: 25000
  edge_threshold: 5
  poll_interval_ms: 10
  max_clients: 4

client:
  server_address: "server:25000"
  reconnect:
    enabled: true
    max_attempts: 5
    delay_seconds: 1.0

protocol:
  version: "2.0.0"
  buffer_size: 4096
  keepalive_interval: 30

logging:
  level: "INFO"
  format: "%(message)s"
"""
        )

        config = ConfigLoader.configWithOverrides_load(
            config_file,
            name="OverriddenName",
            host="127.0.0.1",
            port=30000,
            edge_threshold=10,
        )

        assert config.server.name == "OverriddenName"
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 30000
        assert config.server.edge_threshold == 10

    def test_configWithOverrides_load_client_overrides(self, tmp_path):
        """Test applying client config overrides"""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
server:
  host: "0.0.0.0"
  port: 25000
  edge_threshold: 5
  poll_interval_ms: 10
  max_clients: 4

client:
  server_address: "original:25000"
  reconnect:
    enabled: true
    max_attempts: 5
    delay_seconds: 1.0

protocol:
  version: "2.0.0"
  buffer_size: 4096
  keepalive_interval: 30

logging:
  level: "INFO"
  format: "%(message)s"
"""
        )

        config = ConfigLoader.configWithOverrides_load(
            config_file,
            server_address="overridden:30000",
        )

        assert config.client.server_address == "overridden:30000"

    def test_configWithOverrides_load_none_values_ignored(self, tmp_path):
        """Test that None override values don't override config"""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
server:
  name: "OriginalName"
  host: "0.0.0.0"
  port: 25000
  edge_threshold: 5
  poll_interval_ms: 10
  max_clients: 4

client:
  server_address: "server:25000"
  reconnect:
    enabled: true
    max_attempts: 5
    delay_seconds: 1.0

protocol:
  version: "2.0.0"
  buffer_size: 4096
  keepalive_interval: 30

logging:
  level: "INFO"
  format: "%(message)s"
"""
        )

        config = ConfigLoader.configWithOverrides_load(
            config_file,
            name=None,  # Should not override
            port=30000,  # Should override
        )

        assert config.server.name == "OriginalName"  # Not overridden
        assert config.server.port == 30000  # Overridden


class TestConfigDataclasses:
    """Test config dataclass creation"""

    def test_server_config_creation(self):
        """Test ServerConfig dataclass creation"""
        server = ServerConfig(
            name="TestServer",
            host="0.0.0.0",
            port=25000,
            display=":0",
            edge_threshold=5,
            velocity_threshold=100.0,
            poll_interval_ms=10,
            max_clients=4,
            client_position="west",
            panic_key=PanicKeyConfig(key="F12", modifiers=[]),
            overlay_enabled=True,
        )

        assert server.name == "TestServer"
        assert server.host == "0.0.0.0"
        assert server.port == 25000
        assert server.display == ":0"
        assert server.overlay_enabled is True

    def test_named_client_config_creation(self):
        """Test NamedClientConfig dataclass creation"""
        client = NamedClientConfig(name="laptop", position="west")

        assert client.name == "laptop"
        assert client.position == "west"

    def test_client_reconnect_config_creation(self):
        """Test ClientReconnectConfig dataclass creation"""
        reconnect = ClientReconnectConfig(
            enabled=True,
            max_attempts=5,
            delay_seconds=1.5,
        )

        assert reconnect.enabled is True
        assert reconnect.max_attempts == 5
        assert reconnect.delay_seconds == 1.5
