"""Thin server entrypoint and compatibility exports."""

from __future__ import annotations

import sys
from typing import NoReturn

from tx2tx.server.runtime import arguments_parse, clientMessage_handle, server_run

__all__ = ["arguments_parse", "clientMessage_handle", "server_run", "main"]


def main() -> NoReturn:
    """
    Main entrypoint for tx2tx server CLI.

    Returns:
        NoReturn: Process exits.
    """
    args = arguments_parse()
    try:
        server_run(args)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
