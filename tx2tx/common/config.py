"""Configuration file loading and management"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class ServerConfig:
    """Server configuration settings"""
    host: str
    port: int
    display: Optional[str]
    edge_threshold: int
    poll_interval_ms: int
    max_clients: int
    client_position: str  # Position of client relative to server


@dataclass
class ClientReconnectConfig:
    """Client reconnection settings"""
    enabled: bool
    max_attempts: int
    delay_seconds: float


@dataclass
class ClientConfig:
    """Client configuration settings"""
    server_address: str
    display: Optional[str]
    reconnect: ClientReconnectConfig


@dataclass
class ProtocolConfig:
    """Protocol configuration settings"""
    version: str
    buffer_size: int
    keepalive_interval: int


@dataclass
class LoggingConfig:
    """Logging configuration settings"""
    level: str
    file: Optional[str]
    format: str


@dataclass
class Config:
    """Complete application configuration"""
    server: ServerConfig
    client: ClientConfig
    protocol: ProtocolConfig
    logging: LoggingConfig


class ConfigLoader:
    """Loads and parses configuration from YAML files"""

    DEFAULT_CONFIG_PATHS = [
        "config.yml",
        "~/.config/tx2tx/config.yml",
        "/etc/tx2tx/config.yml",
    ]

    @staticmethod
    def configFile_find() -> Optional[Path]:
        """
        Find configuration file in standard locations

        Returns:
            Path to config file, or None if not found
        """
        for config_path in ConfigLoader.DEFAULT_CONFIG_PATHS:
            path = Path(config_path).expanduser().resolve()
            if path.exists() and path.is_file():
                return path
        return None

    @staticmethod
    def yaml_load(file_path: Path) -> Dict[str, Any]:
        """
        Load YAML configuration file

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed configuration dictionary

        Raises:
            FileNotFoundError: If file does not exist
            yaml.YAMLError: If file is not valid YAML
        """
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Config file {file_path} must contain a YAML dictionary")

        return data

    @staticmethod
    def config_parse(data: Dict[str, Any]) -> Config:
        """
        Parse configuration dictionary into Config object

        Args:
            data: Raw configuration dictionary

        Returns:
            Parsed Config object

        Raises:
            KeyError: If required configuration keys are missing
        """
        # Parse server config
        server_data = data["server"]
        server = ServerConfig(
            host=server_data["host"],
            port=server_data["port"],
            display=server_data.get("display"),
            edge_threshold=server_data["edge_threshold"],
            poll_interval_ms=server_data["poll_interval_ms"],
            max_clients=server_data["max_clients"],
            client_position=server_data.get("client_position", "west"),  # Default to west
        )

        # Parse client config
        client_data = data["client"]
        reconnect_data = client_data["reconnect"]
        reconnect = ClientReconnectConfig(
            enabled=reconnect_data["enabled"],
            max_attempts=reconnect_data["max_attempts"],
            delay_seconds=reconnect_data["delay_seconds"],
        )
        client = ClientConfig(
            server_address=client_data["server_address"],
            display=client_data.get("display"),
            reconnect=reconnect,
        )

        # Parse protocol config
        protocol_data = data["protocol"]
        protocol = ProtocolConfig(
            version=protocol_data["version"],
            buffer_size=protocol_data["buffer_size"],
            keepalive_interval=protocol_data["keepalive_interval"],
        )

        # Parse logging config
        logging_data = data["logging"]
        logging = LoggingConfig(
            level=logging_data["level"],
            file=logging_data.get("file"),
            format=logging_data["format"],
        )

        return Config(
            server=server,
            client=client,
            protocol=protocol,
            logging=logging,
        )

    @staticmethod
    def config_load(file_path: Optional[Path] = None) -> Config:
        """
        Load configuration from file

        Args:
            file_path: Optional path to config file. If None, searches standard locations.

        Returns:
            Parsed Config object

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config file is invalid
        """
        if file_path is None:
            file_path = ConfigLoader.configFile_find()
            if file_path is None:
                raise FileNotFoundError(
                    f"Config file not found in standard locations: "
                    f"{ConfigLoader.DEFAULT_CONFIG_PATHS}"
                )

        data = ConfigLoader.yaml_load(file_path)
        return ConfigLoader.config_parse(data)

    @staticmethod
    def configWithOverrides_load(
        file_path: Optional[Path] = None,
        **overrides: Any
    ) -> Config:
        """
        Load configuration and apply command-line overrides

        Args:
            file_path: Optional path to config file
            **overrides: Key-value pairs to override config values

        Returns:
            Config object with overrides applied

        Example:
            config = ConfigLoader.configWithOverrides_load(
                host="127.0.0.1",
                port=25000
            )
        """
        config = ConfigLoader.config_load(file_path)

        # Apply overrides to server config
        if "host" in overrides and overrides["host"] is not None:
            config.server.host = overrides["host"]
        if "port" in overrides and overrides["port"] is not None:
            config.server.port = overrides["port"]
        if "display" in overrides:
            config.server.display = overrides["display"]
        if "edge_threshold" in overrides and overrides["edge_threshold"] is not None:
            config.server.edge_threshold = overrides["edge_threshold"]

        # Apply overrides to client config
        if "server_address" in overrides and overrides["server_address"] is not None:
            config.client.server_address = overrides["server_address"]

        return config
