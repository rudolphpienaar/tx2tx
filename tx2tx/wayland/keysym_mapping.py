"""Wayland evdev-to-keysym mapping helpers."""

from __future__ import annotations

from typing import Optional

_KEYCODE_TO_KEYNAME: dict[int, str] | None = None
_KEYCODE_TO_KEYSYM: dict[int, int] | None = None

_SPECIAL_KEYSYM_BY_BASE: dict[str, str] = {
    "ENTER": "Return",
    "ESC": "Escape",
    "SPACE": "space",
    "TAB": "Tab",
    "BACKSPACE": "BackSpace",
    "MINUS": "minus",
    "EQUAL": "equal",
    "LEFTBRACE": "bracketleft",
    "RIGHTBRACE": "bracketright",
    "SEMICOLON": "semicolon",
    "APOSTROPHE": "apostrophe",
    "GRAVE": "grave",
    "BACKSLASH": "backslash",
    "COMMA": "comma",
    "DOT": "period",
    "SLASH": "slash",
    "LEFTSHIFT": "Shift_L",
    "RIGHTSHIFT": "Shift_R",
    "LEFTCTRL": "Control_L",
    "RIGHTCTRL": "Control_R",
    "LEFTALT": "Alt_L",
    "RIGHTALT": "Alt_R",
    "LEFTMETA": "Super_L",
    "RIGHTMETA": "Super_R",
    "CAPSLOCK": "Caps_Lock",
    "DELETE": "Delete",
    "INSERT": "Insert",
    "HOME": "Home",
    "END": "End",
    "PAGEUP": "Page_Up",
    "PAGEDOWN": "Page_Down",
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "PRINT": "Print",
    "PAUSE": "Pause",
}


def keysymNameFromKeyBase_get(base: str) -> str | None:
    """
    Map an evdev KEY_* base token to an X11 keysym name.

    Args:
        base: Key name without KEY_ prefix.

    Returns:
        X11 keysym name or None when unsupported.
    """
    if base in _SPECIAL_KEYSYM_BY_BASE:
        return _SPECIAL_KEYSYM_BY_BASE[base]
    if len(base) == 1 and base.isalpha():
        return base.lower()
    if base.isdigit():
        return base
    if base.startswith("F") and base[1:].isdigit():
        return base
    return None


def _mappingTables_init() -> bool:
    """
    Initialize evdev->keysym caches lazily.

    Returns:
        True when mapping tables are available.
    """
    try:
        from evdev import ecodes
        from Xlib import XK
    except Exception:
        return False

    global _KEYCODE_TO_KEYNAME, _KEYCODE_TO_KEYSYM
    if _KEYCODE_TO_KEYSYM is not None and _KEYCODE_TO_KEYNAME is not None:
        return True

    keyname_mapping: dict[int, str] = keynameMapping_build(ecodes.KEY.items())
    keysym_mapping: dict[int, int] = keysymMapping_build(keyname_mapping, XK)

    _KEYCODE_TO_KEYNAME = keyname_mapping
    _KEYCODE_TO_KEYSYM = keysym_mapping
    return True


def keynameMapping_build(key_items) -> dict[int, str]:
    """
    Build mapping from evdev keycode to key name.

    Args:
        key_items: Iterable of `(name, value)` tuples from evdev `ecodes.KEY`.

    Returns:
        Keycode-to-name map.
    """
    keyname_mapping: dict[int, str] = {}
    for name, value in key_items:
        if not isinstance(name, str) or not name.startswith("KEY_"):
            continue
        if isinstance(value, int):
            keyname_mapping.setdefault(value, name)
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, int):
                    keyname_mapping.setdefault(item, name)
    return keyname_mapping


def keysymMapping_build(keyname_mapping: dict[int, str], xk_module) -> dict[int, int]:
    """
    Build mapping from evdev keycode to X11 keysym integer.

    Args:
        keyname_mapping: Keycode-to-name map.
        xk_module: Imported `Xlib.XK` module.

    Returns:
        Keycode-to-keysym map.
    """
    keysym_mapping: dict[int, int] = {}
    for code, key_name in keyname_mapping.items():
        base: str = key_name[4:]
        keysym_name: str | None = keysymNameFromKeyBase_get(base)
        if keysym_name is None:
            continue
        keysym: int = xk_module.string_to_keysym(keysym_name)
        if keysym != 0:
            keysym_mapping[code] = keysym
    return keysym_mapping


def keysymFromEvdevKeycode_get(keycode: int) -> Optional[int]:
    """
    Resolve X11 keysym from evdev keycode.

    Args:
        keycode: evdev keycode.

    Returns:
        X11 keysym integer or None.
    """
    initialized_ok: bool = _mappingTables_init()
    if not initialized_ok:
        return None

    from Xlib import XK

    assert _KEYCODE_TO_KEYSYM is not None
    assert _KEYCODE_TO_KEYNAME is not None
    keysym: int | None = _KEYCODE_TO_KEYSYM.get(keycode)
    if keysym is not None:
        return keysym

    key_name: str | None = _KEYCODE_TO_KEYNAME.get(keycode)
    if key_name is None or not key_name.startswith("KEY_"):
        return None

    base: str = key_name[4:]
    keysym_name = keysymNameFromKeyBase_get(base)
    if keysym_name is None:
        return None
    fallback_keysym: int = XK.string_to_keysym(keysym_name)
    if fallback_keysym == 0:
        return None
    return fallback_keysym
