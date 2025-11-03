"""tx2tx unified command-line interface"""

import argparse
import sys
from typing import NoReturn, Optional

from tx2tx import __version__


def arguments_parse() -> argparse.Namespace:
    """
    Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="tx2tx",
        description="X11 KVM for termux-x11: share mouse/keyboard between X11 displays"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"tx2tx {__version__}"
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--server",
        action="store_true",
        help="Run as server (captures and broadcasts events)"
    )
    mode_group.add_argument(
        "--client",
        type=str,
        metavar="HOST:PORT",
        help="Run as client, connecting to server (e.g., 192.168.1.100:24800)"
    )

    # Common options
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: search standard locations)"
    )

    parser.add_argument(
        "--display",
        type=str,
        default=None,
        help="X11 display name (overrides config)"
    )

    # Server-specific options
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="[Server] Host address to bind to (overrides config)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="[Server] Port to listen on (overrides config)"
    )

    parser.add_argument(
        "--edge-threshold",
        type=int,
        default=None,
        dest="edge_threshold",
        help="[Server] Pixels from edge to trigger transition (overrides config)"
    )

    return parser.parse_args()


def main() -> NoReturn:
    """Main entry point for unified tx2tx command"""
    args = arguments_parse()

    try:
        if args.server:
            # Import and run server
            from tx2tx.server.main import server_run
            server_run(args)
        elif args.client:
            # Import and run client
            from tx2tx.client.main import client_run
            # Rename client arg to server for compatibility with client_run
            args.server = args.client
            client_run(args)
        else:
            print("Error: Must specify --server or --client mode", file=sys.stderr)
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
