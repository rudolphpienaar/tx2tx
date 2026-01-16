"""tx2tx unified command-line interface"""

import argparse
import sys
from typing import NoReturn

from tx2tx import __version__


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments

    Returns:
        Parsed arguments
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
        "--no-overlay",
        action="store_true",
        default=None,
        help="[Server] Disable fullscreen overlay window (cursor will remain visible)",
    )

    parser.add_argument(
        "--client", type=str, default=None, help="[Client] Client name from config (e.g., 'phomux')"
    )

    return parser.parse_args()


def main() -> NoReturn:
    """Main entry point for unified tx2tx command"""
    args = arguments_parse()

    try:
        if args.server or args.client:
            # --server or --client specified: run as client
            # If --client is specified, treat it as client name if --name not provided
            if args.client and not args.name:
                args.name = args.client

            from tx2tx.client.main import client_run

            client_run(args)
        else:
            # No --server or --client: run as server
            from tx2tx.server.main import server_run

            # Handle negative flag
            if args.no_overlay:
                # If flag is set, overlay_enabled is False
                setattr(args, "overlay_enabled", False)
            else:
                setattr(args, "overlay_enabled", None)  # Let config decide

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
