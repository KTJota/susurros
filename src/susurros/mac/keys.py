"""Key tables for macOS. Pure data and logic: no macOS imports, testable on any system.

The rest of the app (shortcut filter, stored settings, key names) works with Windows virtual
key codes. The macOS listener translates each macOS key code into the matching Windows code,
so all of that is shared and a shortcut is stored the same way on both systems.
"""
from __future__ import annotations

VK_FN = 0xFF            # the Fn / Globe key has no Windows code: an otherwise unused one
UNMAPPED = 0x100        # keys without a Windows equivalent: 0x100 + macOS key code
KEYCODE_CAPS_LOCK = 57
KEYCODE_V, KEYCODE_RETURN = 9, 36
OWN_EVENT = 0x53555355  # marks the events Susurros types itself, so the listener skips them

# macOS virtual key code -> Windows virtual key code.
_TO_VK = {
    # letters (macOS codes follow the physical ANSI layout)
    0: 0x41, 11: 0x42, 8: 0x43, 2: 0x44, 14: 0x45, 3: 0x46, 5: 0x47, 4: 0x48, 34: 0x49, 38: 0x4A,
    40: 0x4B, 37: 0x4C, 46: 0x4D, 45: 0x4E, 31: 0x4F, 35: 0x50, 12: 0x51, 15: 0x52, 1: 0x53,
    17: 0x54, 32: 0x55, 9: 0x56, 13: 0x57, 7: 0x58, 16: 0x59, 6: 0x5A,
    # digits
    29: 0x30, 18: 0x31, 19: 0x32, 20: 0x33, 21: 0x34, 23: 0x35, 22: 0x36, 26: 0x37, 28: 0x38, 25: 0x39,
    # punctuation (Windows "OEM" keys)
    41: 0xBA, 24: 0xBB, 43: 0xBC, 27: 0xBD, 47: 0xBE, 44: 0xBF, 50: 0xC0, 33: 0xDB, 42: 0xDC,
    30: 0xDD, 39: 0xDE, 10: 0xE2,
    # editing and navigation
    36: 0x0D, 48: 0x09, 49: 0x20, 51: 0x08, 53: 0x1B, 117: 0x2E, 114: 0x2D,
    115: 0x24, 119: 0x23, 116: 0x21, 121: 0x22, 123: 0x25, 126: 0x26, 124: 0x27, 125: 0x28,
    # modifiers: Command is the Windows key, Option is Alt
    55: 0x5B, 54: 0x5C, 56: 0xA0, 60: 0xA1, 59: 0xA2, 62: 0xA3, 58: 0xA4, 61: 0xA5,
    KEYCODE_CAPS_LOCK: 0x14, 63: VK_FN,
    # function keys
    122: 0x70, 120: 0x71, 99: 0x72, 118: 0x73, 96: 0x74, 97: 0x75, 98: 0x76, 100: 0x77, 101: 0x78,
    109: 0x79, 103: 0x7A, 111: 0x7B, 105: 0x7C, 107: 0x7D, 113: 0x7E, 106: 0x7F, 64: 0x80,
    79: 0x81, 80: 0x82, 90: 0x83,
    # numeric keypad
    82: 0x60, 83: 0x61, 84: 0x62, 85: 0x63, 86: 0x64, 87: 0x65, 88: 0x66, 89: 0x67, 91: 0x68,
    92: 0x69, 67: 0x6A, 69: 0x6B, 78: 0x6D, 65: 0x6E, 75: 0x6F,
}
# Windows virtual key code -> the macOS key codes that produce it.
VK_TO_KEYCODES: dict[int, tuple[int, ...]] = {}
for _keycode, _vk in _TO_VK.items():
    VK_TO_KEYCODES[_vk] = (*VK_TO_KEYCODES.get(_vk, ()), _keycode)

# CGEventFlags bits of each modifier, and the key codes that set them.
FLAG_SHIFT, FLAG_CONTROL, FLAG_OPTION, FLAG_COMMAND, FLAG_FN = 0x20000, 0x40000, 0x80000, 0x100000, 0x800000
_MODIFIER_FLAG = {56: FLAG_SHIFT, 60: FLAG_SHIFT, 59: FLAG_CONTROL, 62: FLAG_CONTROL,
                  58: FLAG_OPTION, 61: FLAG_OPTION, 55: FLAG_COMMAND, 54: FLAG_COMMAND, 63: FLAG_FN}

# The shared key names are the Windows ones; these are what the same keys are called on a Mac.
_MAC_NAMES = {
    "Ctrl": "Control", "Left Ctrl": "Left Control", "Right Ctrl": "Right Control",
    "Alt": "Option", "Left Alt": "Left Option", "Right Alt": "Right Option",
    "Win": "Command", "Right Win": "Right Command",
}
# Keys that the shared table does not name and that are the same on every keyboard layout.
_FIXED_LABELS = {
    VK_FN: "Fn", 0x0D: "Return", 0x08: "Delete", 0x1B: "Esc", 0x2E: "Forward Delete",
    0x24: "Home", 0x23: "End", 0x21: "Page Up", 0x22: "Page Down",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
}


def to_vk(keycode: int) -> int:
    """The Windows virtual key code that stands for a macOS key code."""
    return _TO_VK.get(keycode, UNMAPPED + keycode)


def mac_name(name: str) -> str:
    """What macOS calls a key that the shared table names the Windows way."""
    return _MAC_NAMES.get(name, name)


def label(vk: int, typed: str = "") -> str:
    """Name for a key the shared table cannot name: a fixed one, or the character it types."""
    if vk in _FIXED_LABELS:
        return _FIXED_LABELS[vk]
    typed = typed.strip()
    return typed.upper() if typed and typed.isprintable() else f"Key {vk}"


def modifier_is_down(keycode: int, flags: int, held: set[int]) -> bool | None:
    """macOS reports modifiers as "the flags changed", without saying whether the key went down
    or up. Works that out from the flags and from `held`, the modifier key codes known to be
    down, which it keeps up to date. None for keys that cannot be followed (Caps Lock: macOS
    reports when the light changes, not when the key is pressed and released)."""
    flag = _MODIFIER_FLAG.get(keycode)
    if flag is None:
        return None
    if not flags & flag:
        # The flag is off: this key and its twin on the other side are both up.
        held.difference_update([k for k, f in _MODIFIER_FLAG.items() if f == flag])
        return False
    if keycode in held:
        held.discard(keycode)   # the flag stays on because the twin key is still down
        return False
    held.add(keycode)
    return True


def utf16_chunks(text: str, size: int = 20) -> list[str]:
    """Splits text into pieces of at most `size` UTF-16 units (the most one synthetic key event
    carries), without cutting a character that takes two units in half."""
    chunks, current, units = [], "", 0
    for char in text:
        width = 2 if ord(char) > 0xFFFF else 1
        if units + width > size:
            chunks.append(current)
            current, units = "", 0
        current += char
        units += width
    if current:
        chunks.append(current)
    return chunks
