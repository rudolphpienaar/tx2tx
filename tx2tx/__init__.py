"""
tx2tx: network input sharing across X11 and Wayland backends.
Seamless mouse/keyboard sharing across heterogeneous desktops.
"""

import subprocess
from pathlib import Path


def _gitHash_get() -> str:
    """
    Get short git hash, or 'dev' if not in git repo
    
    Args:
        None.
    
    Returns:
        Result value.
    """
    """Get short git hash, or 'dev' if not in git repo"""
    try:
        repo_path = Path(__file__).parent.parent
        result = subprocess.run(
            ["git", "rev-parse", "--short=4", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "dev"


__version__ = f"4.0.36.{_gitHash_get()}"
__author__ = "tx2tx contributors"
