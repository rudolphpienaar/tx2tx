"""tx2tx unified command-line interface"""

import argparse
import sys
from typing import NoReturn

from tx2tx import __version__


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments
    
    Args:
        None.
    
    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        prog="tx2tx",
        description="X11 KVM for termux-x11: share mouse/keyboard between X11 displays",
    )

    parser.add_argument("--version", action="version", version=f"tx2tx {__version__}")

    # Mode selection: --server means client mode (connect to server)
    # No --server means run as server
    parser.add_argument(
        "--server",
        type=str,
        metavar="HOST:PORT",
        default=None,
        help="Connect to server at HOST:PORT (client mode). If omitted, run as server.",
    )

    # Common options
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)",
    )

    parser.add_argument(
        "--display", type=str, default=None, help="X11 display name (overrides config)"
    )

    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        help="Input backend to use (e.g., x11, wayland). Defaults to x11.",
    )

    parser.add_argument(
        "--wayland-helper",
        type=str,
        default=None,
        help="Wayland helper command for privileged input operations.",
    )

    parser.add_argument(
        "--wayland-calibrate",
        action="store_true",
        help="Wayland: warp cursor to center on startup to sync helper state.",
    )

    parser.add_argument(
        "--wayland-screen-width",
        type=int,
        default=None,
        help="Wayland screen width override (pixels).",
    )

    parser.add_argument(
        "--wayland-screen-height",
        type=int,
        default=None,
        help="Wayland screen height override (pixels).",
    )

    parser.add_argument(
        "--wayland-pointer-provider",
        type=str,
        choices=["helper", "gnome"],
        default=None,
        help="Wayland pointer coordinate provider (server mode; default: helper).",
    )

    # Server-specific options
    parser.add_argument(
        "--host", type=str, default=None, help="[Server] Host address to bind to (overrides config)"
    )

    parser.add_argument(
        "--port", type=int, default=None, help="[Server] Port to listen on (overrides config)"
    )

    parser.add_argument(
        "--edge-threshold",
        type=int,
        default=None,
        dest="edge_threshold",
        help="[Server] Pixels from edge to trigger transition (overrides config)",
    )

    parser.add_argument(
        "--name", type=str, default=None, help="[Server] Server name for logging (overrides config)"
    )

    parser.add_argument(
        "--overlay",
        action="store_true",
        help="[Server] Enable fullscreen overlay window to hide cursor (Crostini workaround)",
    )

    parser.add_argument(
        "--x11native",
        action="store_true",
        help="[Server] Optimize for native X11 (disables Crostini workarounds, uses blank cursor)",
    )

    parser.add_argument(
        "--software-cursor",
        action="store_true",
        help="[Client] Enable software rendered cursor (useful if hardware cursor is invisible)",
    )

    parser.add_argument(
        "--client", type=str, default=None, help="[Client] Client name from config (e.g., 'phomux')"
    )

    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging (overrides config)"
    )

    parser.add_argument(
        "--info", action="store_true", help="Enable info logging (overrides config)"
    )

    parser.add_argument(
        "--warning", action="store_true", help="Enable warning logging (overrides config)"
    )

    parser.add_argument(
        "--error", action="store_true", help="Enable error logging (overrides config)"
    )

    parser.add_argument(
        "--critical", action="store_true", help="Enable critical logging (overrides config)"
    )

    return parser.parse_args()


def main() -> NoReturn:
    """
    Main entry point for unified tx2tx command
    
    Args:
        None.
    
    Returns:
        Result value.
    """
    """Main entry point for unified tx2tx command"""
    args = arguments_parse()

    # Determine logging level override
    log_level_override = None
    if args.debug:
        log_level_override = "DEBUG"
    elif args.info:
        log_level_override = "INFO"
    elif args.warning:
        log_level_override = "WARNING"
    elif args.error:
        log_level_override = "ERROR"
    elif args.critical:
        log_level_override = "CRITICAL"

    try:
        if args.server or args.client or args.software_cursor:
            # --server, --client, or --software-cursor specified: run as client
            # If --client is specified, treat it as client name if --name not provided
            if args.client and not args.name:
                args.name = args.client

            from tx2tx.client.main import client_run
            
            if log_level_override:
                setattr(args, "log_level", log_level_override)

            client_run(args)
        else:
            # No client-related flags: run as server
            from tx2tx.server.main import server_run

            if log_level_override:
                setattr(args, "log_level", log_level_override)

            # Handle overlay flag
            if args.overlay:
                setattr(args, "overlay_enabled", True)
            else:
                setattr(args, "overlay_enabled", None)  # Let config decide

            # Handle x11native flag (takes precedence over overlay)
            if args.x11native:
                setattr(args, "x11native", True)
                setattr(args, "overlay_enabled", False)  # Force disable overlay on native X11
            else:
                setattr(args, "x11native", False)

            server_run(args)
        # Both client_run and server_run are NoReturn, so this is unreachable
        # But we need explicit exit for mypy
        sys.exit(0)

    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
