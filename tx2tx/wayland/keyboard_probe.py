"""Wayland keyboard capture probe using the existing helper pipeline."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass

from tx2tx.wayland.helper import WaylandHelperClient


@dataclass
class ProbeConfig:
    """Runtime configuration for the keyboard probe."""

    helper_command: str
    poll_interval_sec: float


class KeyboardProbe:
    """Probe that grabs keyboard devices and streams captured key events."""

    def __init__(self, config: ProbeConfig) -> None:
        """
        Initialize keyboard probe.

        Args:
            config: Probe runtime configuration.
        """
        self._config: ProbeConfig = config
        self._helper: WaylandHelperClient = WaylandHelperClient(config.helper_command)
        self._running: bool = True

    def signalHandle_requestStop(self, signum: int, _frame) -> None:
        """
        Request clean shutdown on POSIX signal.

        Args:
            signum: Received signal number.
            _frame: Python frame object (unused).
        """
        _ = signum
        self._running = False

    def run(self) -> int:
        """
        Start probe loop.

        Returns:
            Process exit code.
        """
        self._helper.connection_establish()

        grab_result: dict[str, int | list[str]] = self._helper.keyboard_grab()
        grabbed_count: int = int(grab_result.get("grabbed", 0))
        failed_count: int = int(grab_result.get("failed", 0))
        grabbed_devices: list[str] = list(grab_result.get("grabbed_devices", []))
        failed_devices: list[str] = list(grab_result.get("failed_devices", []))

        print(
            f"[KEYBOARD_GRAB] grabbed={grabbed_count} failed={failed_count}",
            flush=True,
        )
        print(f"[KEYBOARD_GRAB] grabbed_devices={grabbed_devices}", flush=True)
        print(f"[KEYBOARD_GRAB] failed_devices={failed_devices}", flush=True)

        if grabbed_count <= 0:
            print(
                "[ERROR] No keyboard devices grabbed. Key capture will not work.",
                file=sys.stderr,
                flush=True,
            )
            return 2

        while self._running:
            events, modifier_state = self._helper.inputEvents_read()
            for event in events:
                event_type: str = str(event.get("event_type", "unknown"))
                if not event_type.startswith("key_"):
                    continue
                keycode: int | None = (
                    int(event["keycode"]) if event.get("keycode") is not None else None
                )
                state_value: int = (
                    int(event["state"]) if event.get("state") is not None else modifier_state
                )
                source_device: str = str(event.get("source_device", "unknown"))
                timestamp: str = time.strftime("%Y-%m-%d %H:%M:%S")
                print(
                    f"{timestamp} [{event_type}] keycode={keycode} state=0x{state_value:x} device={source_device}",
                    flush=True,
                )
            time.sleep(self._config.poll_interval_sec)

        return 0

    def shutdown(self) -> None:
        """
        Release keyboard grab and close helper connection.
        """
        try:
            _ = self._helper.keyboard_ungrab()
        except Exception:
            pass
        self._helper.connection_close()


def arguments_parse() -> ProbeConfig:
    """
    Parse CLI arguments into probe configuration.

    Returns:
        Parsed probe configuration.
    """
    parser = argparse.ArgumentParser(
        description="Wayland keyboard capture probe (uses tx2tx helper)."
    )
    parser.add_argument(
        "--helper",
        required=True,
        help="Helper command string (e.g. './.venv/bin/tx2tx-wayland-helper').",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.01,
        help="Polling interval in seconds (default: 0.01).",
    )
    args = parser.parse_args()
    return ProbeConfig(
        helper_command=str(args.helper),
        poll_interval_sec=float(args.poll_interval),
    )


def main() -> int:
    """
    CLI entrypoint for keyboard probe.

    Returns:
        Exit code.
    """
    config: ProbeConfig = arguments_parse()
    probe: KeyboardProbe = KeyboardProbe(config)
    signal.signal(signal.SIGINT, probe.signalHandle_requestStop)
    signal.signal(signal.SIGTERM, probe.signalHandle_requestStop)

    try:
        return probe.run()
    finally:
        probe.shutdown()


if __name__ == "__main__":
    sys.exit(main())
