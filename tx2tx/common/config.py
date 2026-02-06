"""Configuration file loading and management"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class NamedClientConfig:
    """Named client configuration (for server's clients list)"""

    name: str
    position: str  # "west", "east", "north", "south"


@dataclass
class PanicKeyConfig:
    """Panic key configuration for emergency return to CENTER"""

    key: str  # Key name (e.g., "Scroll_Lock", "F12", "Escape")
    modifiers: list[str]  # Modifier keys (e.g., ["Ctrl", "Shift"])


@dataclass
class ServerConfig:
    """Server configuration settings"""

    name: str
    host: str
    port: int
    display: Optional[str]
    edge_threshold: int
    velocity_threshold: float  # Minimum velocity (px/s) to cross boundary
    poll_interval_ms: int
    max_clients: int
    client_position: str  # DEPRECATED: Position of client relative to server
    panic_key: PanicKeyConfig  # Panic key to force return to CENTER
    overlay_enabled: bool  # Whether to use overlay window for cursor hiding


@dataclass
class ClientReconnectConfig:
    """Client reconnection settings"""

    enabled: bool
    max_attempts: int
    delay_seconds: float


@dataclass
class ClientConnectionConfig:
    """Client connection configuration settings"""

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
class WaylandConfig:
    """Wayland backend settings"""

    helper_command: Optional[str]
    screen_width: Optional[int]
    screen_height: Optional[int]
    calibrate: bool
    pointer_provider: str


@dataclass
class BackendConfig:
    """Backend selection and settings"""

    name: str
    wayland: WaylandConfig


@dataclass
class Config:
    """Complete application configuration"""

    server: ServerConfig
    clients: list[NamedClientConfig]
    client: ClientConnectionConfig
    protocol: ProtocolConfig
    logging: LoggingConfig
    backend: BackendConfig


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
        
        Args:
            None.
        
        Returns:
            Path to config file or None.
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

        # Parse panic key config (default: Scroll_Lock with no modifiers)
        panic_key_data = server_data.get("panic_key", {})
        if isinstance(panic_key_data, str):
            # Simple format: just a key name like "Scroll_Lock" or "Ctrl+Shift+Escape"
            if "+" in panic_key_data:
                parts = panic_key_data.split("+")
                panic_key = PanicKeyConfig(key=parts[-1], modifiers=parts[:-1])
            else:
                panic_key = PanicKeyConfig(key=panic_key_data, modifiers=[])
        else:
            # Dict format: {key: "Escape", modifiers: ["Ctrl", "Shift"]}
            panic_key = PanicKeyConfig(
                key=panic_key_data.get("key", "Scroll_Lock"),
                modifiers=panic_key_data.get("modifiers", []),
            )

        server = ServerConfig(
            name=server_data.get("name", "TX2TX"),  # Default to TX2TX
            host=server_data["host"],
            port=server_data["port"],
            display=server_data.get("display"),
            edge_threshold=server_data["edge_threshold"],
            velocity_threshold=server_data.get("velocity_threshold", 100.0),  # Default 100 px/s
            poll_interval_ms=server_data["poll_interval_ms"],
            max_clients=server_data["max_clients"],
            client_position=server_data.get(
                "client_position", "west"
            ),  # DEPRECATED: Default to west
            panic_key=panic_key,
            overlay_enabled=server_data.get("overlay_enabled", False),
        )

        # Parse named clients list
        clients_data = data.get("clients", [])
        clients = [
            NamedClientConfig(name=client_entry["name"], position=client_entry["position"])
            for client_entry in clients_data
        ]

        # Parse client connection config
        client_data = data["client"]
        reconnect_data = client_data["reconnect"]
        reconnect = ClientReconnectConfig(
            enabled=reconnect_data["enabled"],
            max_attempts=reconnect_data["max_attempts"],
            delay_seconds=reconnect_data["delay_seconds"],
        )
        client = ClientConnectionConfig(
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

        # Parse backend config (optional)
        backend_data = data.get("backend", {})
        backend_name = backend_data.get("name", "x11")
        wayland_data = backend_data.get("wayland", {})
        wayland = WaylandConfig(
            helper_command=wayland_data.get("helper_command"),
            screen_width=wayland_data.get("screen_width"),
            screen_height=wayland_data.get("screen_height"),
            calibrate=bool(wayland_data.get("calibrate", False)),
            pointer_provider=str(wayland_data.get("pointer_provider", "helper")),
        )
        backend = BackendConfig(name=backend_name, wayland=wayland)

        return Config(
            server=server,
            clients=clients,
            client=client,
            protocol=protocol,
            logging=logging,
            backend=backend,
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
    def configWithOverrides_load(file_path: Optional[Path] = None, **overrides: Any) -> Config:
        """
        Load configuration and apply command-line overrides
        
        Args:
            file_path: Optional path to config file
            overrides: overrides value.
        
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
        if "name" in overrides and overrides["name"] is not None:
            config.server.name = overrides["name"]
        if "host" in overrides and overrides["host"] is not None:
            config.server.host = overrides["host"]
        if "port" in overrides and overrides["port"] is not None:
            config.server.port = overrides["port"]
        if "display" in overrides:
            config.server.display = overrides["display"]
        if "edge_threshold" in overrides and overrides["edge_threshold"] is not None:
            config.server.edge_threshold = overrides["edge_threshold"]
        if "overlay_enabled" in overrides and overrides["overlay_enabled"] is not None:
            config.server.overlay_enabled = overrides["overlay_enabled"]

        # Apply overrides to client config
        if "server_address" in overrides and overrides["server_address"] is not None:
            config.client.server_address = overrides["server_address"]

        return config
