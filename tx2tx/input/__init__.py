"""Backend abstraction layer for input capture and injection."""

from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent, InputInjector
from tx2tx.input.factory import clientBackend_create, serverBackend_create

__all__ = [
    "DisplayBackend",
    "InputCapturer",
    "InputEvent",
    "InputInjector",
    "clientBackend_create",
    "serverBackend_create",
]
